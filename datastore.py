"""
datastore.py
================
Request-safe data layer for the Local Development Tracker.

Why this module exists
----------------------
``queries.py`` reads every dataset live from Databricks Unity Catalog with
``SELECT *`` full-table scans and a Python-level row assembler. Doing that on
the web-request path is what made the app slow and, under load, unresponsive:
the home page alone triggered six full-table reads plus three dataset
assemblies before it could render two numbers, and the 300-second in-memory
TTL meant a user hit that cost again every five minutes.

The Unity Catalog tables only change on a data-release cadence, so this module
treats the assembled datasets as **build artifacts**:

* ``warm()`` runs the Databricks assemblers *once*, off the request path, and
  writes gzipped-JSON artifacts to a writable cache directory.
* The public accessors (:func:`analytics_dataset`, :func:`boundary_geojson`,
  :func:`strategy_inventory`, :func:`home_summary`) resolve, in order, from an
  in-process memo, the writable cache, a snapshot directory shipped with the
  deployment (``scripts/build_snapshot.py``), and finally the legacy bundled
  files under ``assets/data/<country>/``. They **never** call Databricks
  synchronously -- a stale or missing artifact schedules a background refresh
  and serves the best copy available in the meantime.

Net effect: every page renders from a local dict lookup. The only time a user
waits for Databricks is never; the only time *anything* waits for Databricks
is the background warm, which is invisible.

``queries.py`` keeps working stand-alone (and in the test-suite) because the
providers it calls are pluggable -- importing this module swaps them for the
cache-backed versions via :func:`queries.set_data_providers`.
"""

from __future__ import annotations

import gzip
import json
import logging
import math
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import constants
import queries

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Locations
# --------------------------------------------------------------------------

_REPO_DIR = os.path.dirname(os.path.abspath(__file__))
_ASSETS_DIR = os.path.join(_REPO_DIR, "assets")

# Writable, runtime-refreshed artifacts. On Posit Connect point this at a
# persistent, writable content directory; locally it defaults to ./.ldt_cache.
CACHE_DIR = os.environ.get("LDT_CACHE_DIR", os.path.join(_REPO_DIR, ".ldt_cache"))

# Read-only artifacts shipped with the deployment, produced before deploy by
# ``python scripts/build_snapshot.py``. This is what makes the *first* request
# after a fresh deploy instant even before the background warm finishes.
SNAPSHOT_DIR = os.environ.get(
    "LDT_SNAPSHOT_DIR", os.path.join(_ASSETS_DIR, "data", "_snapshot")
)

# A warm is scheduled in the background when the newest artifact is older than
# this. Release-cadence data -> 12h is plenty; lower it if releases are daily.
DATA_MAX_AGE_SECONDS = int(os.environ.get("LDT_DATA_MAX_AGE_SECONDS", str(12 * 3600)))

# After a failed warm, wait this long before trying again (don't hammer a
# warehouse that is down).
_WARM_RETRY_COOLDOWN_SECONDS = int(os.environ.get("LDT_WARM_RETRY_COOLDOWN_SECONDS", "600"))

_BG_WARM_DISABLED = os.environ.get("LDT_DISABLE_BG_WARM", "0") == "1"

# Token gate for the POST /ldt/admin/refresh route wired up in app.py.
REFRESH_TOKEN = os.environ.get("LDT_REFRESH_TOKEN", "")


# --------------------------------------------------------------------------
# In-process memo (per worker) -- the hot path
# --------------------------------------------------------------------------

_MEMO: Dict[str, Any] = {}
_MEMO_LOCK = threading.RLock()

# Functions other modules register to be flushed whenever fresh data lands
# (e.g. analytics_service clears its figure/payload memo).
_INVALIDATION_HOOKS: List[Callable[[], None]] = []


def register_invalidation_hook(fn: Callable[[], None]) -> None:
    """Register ``fn`` to run after every successful warm / refresh."""
    _INVALIDATION_HOOKS.append(fn)


def _run_invalidation_hooks() -> None:
    for fn in list(_INVALIDATION_HOOKS):
        try:
            fn()
        except Exception:  # noqa: BLE001
            logger.exception("data-invalidation hook %r failed", fn)


# --------------------------------------------------------------------------
# JSON <-> disk helpers (atomic writes, gzip for the big ones)
# --------------------------------------------------------------------------

def _json_safe(value: Any) -> Any:
    """Recursively replace NaN/Inf with None so artifacts are valid JSON."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _atomic_write(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def _write_json_gz(path: str, obj: Any) -> None:
    payload = json.dumps(_json_safe(obj), separators=(",", ":")).encode("utf-8")
    _atomic_write(path, gzip.compress(payload, compresslevel=6))


def _write_json(path: str, obj: Any) -> None:
    _atomic_write(path, json.dumps(_json_safe(obj), indent=2).encode("utf-8"))


def _read_json_maybe_gz(path: str) -> Any:
    with open(path, "rb") as fh:
        head = fh.read(2)
        fh.seek(0)
        raw = fh.read()
    if head == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw)


# --------------------------------------------------------------------------
# Artifact path resolution
# --------------------------------------------------------------------------

def _cache_path(name: str) -> str:
    return os.path.join(CACHE_DIR, name)


def _snapshot_path(name: str) -> str:
    return os.path.join(SNAPSHOT_DIR, name)


def _analytics_name(code: str) -> str:
    return f"analytics_{code.upper()}.json.gz"


def _boundary_name(code: str) -> str:
    return f"boundaries_{code.upper()}.json.gz"


def _strategy_name(code: str) -> str:
    return f"strategy_{code.upper()}.json.gz"


_MANIFEST_NAME = "manifest.json"
_HOME_SUMMARY_NAME = "home_summary.json"


def _bundled_analytics_path(code: str) -> Optional[str]:
    country = constants.COUNTRY_BY_CODE.get(code.upper())
    if not country or not country.get("fallback_data_path"):
        return None
    return os.path.join(_ASSETS_DIR, country["fallback_data_path"])


def _bundled_boundary_path(code: str) -> Optional[str]:
    country = constants.COUNTRY_BY_CODE.get(code.upper())
    if not country or not country.get("map_data_path"):
        return None
    return os.path.join(_ASSETS_DIR, country["map_data_path"])


def _resolve(name: str, bundled: Optional[str] = None) -> Optional[str]:
    """First existing of: writable cache, shipped snapshot, legacy bundled."""
    for candidate in (_cache_path(name), _snapshot_path(name), bundled):
        if candidate and os.path.exists(candidate):
            return candidate
    return None


# --------------------------------------------------------------------------
# Memoised artifact load (re-reads only when the file on disk is newer)
# --------------------------------------------------------------------------

def _load_artifact(memo_key: str, name: str, bundled: Optional[str], builder: Callable[[], Any]) -> Any:
    path = _resolve(name, bundled)
    mtime = os.path.getmtime(path) if path else None

    with _MEMO_LOCK:
        cached = _MEMO.get(memo_key)
        if cached is not None and cached[0] == mtime:
            return cached[1]

    if path is not None:
        try:
            value = _read_json_maybe_gz(path)
            with _MEMO_LOCK:
                _MEMO[memo_key] = (mtime, value)
            logger.debug("datastore: loaded %s from %s", memo_key, path)
            _schedule_warm_if_stale()
            return value
        except Exception:  # noqa: BLE001
            logger.exception("datastore: failed to read artifact %s (%s); rebuilding", memo_key, path)

    # Nothing on disk (or it was corrupt): build it live, once, and persist.
    logger.warning("datastore: no artifact for %s; building live from Databricks", memo_key)
    value = builder()
    with _MEMO_LOCK:
        _MEMO[memo_key] = (None, value)
    return value


# --------------------------------------------------------------------------
# Public accessors -- request-path safe, never block on Databricks
# --------------------------------------------------------------------------

def analytics_dataset(country_code: str) -> Dict[str, Any]:
    code = country_code.upper()
    return _load_artifact(
        f"analytics:{code}",
        _analytics_name(code),
        _bundled_analytics_path(code),
        lambda: _backfilled_dataset(code),
    )


def boundary_geojson(country_code: str) -> Dict[str, Any]:
    code = country_code.upper()
    return _load_artifact(
        f"boundaries:{code}",
        _boundary_name(code),
        _bundled_boundary_path(code),
        lambda: queries._assemble_feature_collection(code),
    )


def strategy_inventory(country_code: str) -> Optional[Dict[str, Any]]:
    code = country_code.upper()
    country = constants.COUNTRY_BY_CODE.get(code)
    if not country or country["slug"] not in constants.STRATEGY_INVENTORY_SLUGS:
        return None

    # The strategy inventory is built by walking a Databricks Volume - too slow
    # (and too failure-prone) to do on a request. Serve the artifact if warm()
    # has produced one; otherwise return None and let the page show its
    # "not loaded yet" state while the background warm runs.
    memo_key = f"strategy:{code}"
    path = _resolve(_strategy_name(code))
    mtime = os.path.getmtime(path) if path else None
    with _MEMO_LOCK:
        cached = _MEMO.get(memo_key)
        if cached is not None and cached[0] == mtime:
            return cached[1]
    value = None
    if path is not None:
        try:
            value = _read_json_maybe_gz(path)
        except Exception:  # noqa: BLE001
            logger.exception("datastore: failed to read strategy artifact %s", path)
    with _MEMO_LOCK:
        _MEMO[memo_key] = (mtime, value)
    _schedule_warm_if_stale()
    return value


def home_summary() -> Dict[str, Any]:
    """Tiny payload for the home page: workspace / LSG / latest-year counts."""
    path = _resolve(_HOME_SUMMARY_NAME)
    mtime = os.path.getmtime(path) if path else None
    with _MEMO_LOCK:
        cached = _MEMO.get("home_summary")
        if cached is not None and cached[0] == mtime:
            return cached[1]
    if path is not None:
        try:
            value = _read_json_maybe_gz(path)
            with _MEMO_LOCK:
                _MEMO["home_summary"] = (mtime, value)
            _schedule_warm_if_stale()
            return value
        except Exception:  # noqa: BLE001
            logger.exception("datastore: failed to read home summary; recomputing")
    value = _compute_home_summary()
    with _MEMO_LOCK:
        _MEMO["home_summary"] = (None, value)
    return value


def _compute_home_summary() -> Dict[str, Any]:
    datasets = []
    for country in constants.COUNTRIES:
        try:
            datasets.append(analytics_dataset(country["code"]))
        except Exception:  # noqa: BLE001
            logger.exception("home summary: could not load %s dataset", country["code"])
    total_lsgs = sum(d.get("coverage", {}).get("analyticsMunicipalityCount", 0) for d in datasets)
    years = [d.get("release", {}).get("year") for d in datasets]
    latest_year = max((y for y in years if y), default=None)
    return {
        "countryWorkspaces": len(constants.COUNTRIES),
        "lsgsLoaded": total_lsgs or None,
        "latestYear": latest_year,
    }


def _backfilled_dataset(code: str) -> Dict[str, Any]:
    """Assemble a dataset and fold in map-coverage counts (as warm() does)."""
    dataset = queries._assemble_dataset(code)
    try:
        fc = queries._assemble_feature_collection(code)
        _apply_map_coverage(dataset, fc)
    except Exception:  # noqa: BLE001
        logger.exception("could not compute map coverage for %s during live build", code)
    return dataset


def _apply_map_coverage(dataset: Dict[str, Any], fc: Dict[str, Any]) -> None:
    """Port of the coverage backfill previously done in load_map_feature_collection."""
    boundary_keys = {f["properties"]["compositeKey"] for f in fc.get("features", [])}
    analytics_keys = {m["compositeKey"] for m in dataset["municipalities"]}
    matched = boundary_keys & analytics_keys
    dataset.setdefault("coverage", {})
    dataset["coverage"]["mapMunicipalityCount"] = len(matched)
    dataset["coverage"]["boundaryOnlyCount"] = len(boundary_keys - analytics_keys)
    dataset["mapFeatureKeys"] = sorted(matched)
    for m in dataset["municipalities"]:
        m["mapAvailable"] = m["compositeKey"] in matched


# --------------------------------------------------------------------------
# warm() -- the one place Databricks is read
# --------------------------------------------------------------------------

_WARM_LOCK = threading.Lock()
_warm_state: Dict[str, Any] = {"running": False, "last_ok": None, "last_error": None, "last_attempt": 0.0}


def warm(force: bool = False) -> Dict[str, Any]:
    """Rebuild every artifact from Databricks. Safe to call concurrently:
    only one warm runs at a time; the rest return the current status."""
    if not _WARM_LOCK.acquire(blocking=False):
        logger.info("warm(): already running, skipping duplicate request")
        return manifest()

    _warm_state["running"] = True
    _warm_state["last_attempt"] = time.time()
    started = time.time()
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        built: List[str] = []
        for country in constants.COUNTRIES:
            code = country["code"]
            logger.info("warm(): assembling %s", code)
            dataset = queries._assemble_dataset(code)
            fc = queries._assemble_feature_collection(code)
            _apply_map_coverage(dataset, fc)
            _write_json_gz(_cache_path(_analytics_name(code)), dataset)
            _write_json_gz(_cache_path(_boundary_name(code)), fc)
            built.append(code)
            if country["slug"] in constants.STRATEGY_INVENTORY_SLUGS:
                try:
                    inventory = queries._build_strategy_inventory(code)
                    if inventory:
                        _write_json_gz(_cache_path(_strategy_name(code)), inventory)
                except Exception:  # noqa: BLE001
                    logger.exception("warm(): strategy inventory failed for %s", code)

        with _MEMO_LOCK:
            _MEMO.clear()
        home = _compute_home_summary()
        _write_json(_cache_path(_HOME_SUMMARY_NAME), home)

        man = {
            "built_at": time.time(),
            "built_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration_seconds": round(time.time() - started, 1),
            "countries": built,
            "source": "databricks",
        }
        _write_json(_cache_path(_MANIFEST_NAME), man)

        with _MEMO_LOCK:
            _MEMO.clear()
        queries.clear_caches()
        _run_invalidation_hooks()

        _warm_state["last_ok"] = time.time()
        _warm_state["last_error"] = None
        logger.info("warm(): done in %.1fs (%s)", time.time() - started, ", ".join(built))
        return man
    except Exception as exc:  # noqa: BLE001
        _warm_state["last_error"] = str(exc)
        logger.exception("warm(): failed")
        raise
    finally:
        _warm_state["running"] = False
        _WARM_LOCK.release()


def manifest() -> Dict[str, Any]:
    path = _resolve(_MANIFEST_NAME)
    if path:
        try:
            return _read_json_maybe_gz(path)
        except Exception:  # noqa: BLE001
            pass
    return {}


# --------------------------------------------------------------------------
# Background warm scheduling
# --------------------------------------------------------------------------

_bg_thread: Optional[threading.Thread] = None
_bg_lock = threading.Lock()


def _newest_artifact_age() -> Optional[float]:
    newest: Optional[float] = None
    # Prefer the manifest timestamp; fall back to file mtimes.
    man = manifest()
    if man.get("built_at"):
        return time.time() - float(man["built_at"])
    for country in constants.COUNTRIES:
        p = _resolve(_analytics_name(country["code"]), _bundled_analytics_path(country["code"]))
        if p:
            age = time.time() - os.path.getmtime(p)
            newest = age if newest is None else min(newest, age)
    return newest


def _should_warm() -> bool:
    if _BG_WARM_DISABLED:
        return False
    if _warm_state["running"]:
        return False
    if time.time() - _warm_state["last_attempt"] < _WARM_RETRY_COOLDOWN_SECONDS and _warm_state["last_error"]:
        return False  # cooling down after a failure
    # No cache artifacts at all -> must warm (bundled/snapshot data may be stale).
    have_cache = all(
        os.path.exists(_cache_path(_analytics_name(c["code"]))) for c in constants.COUNTRIES
    )
    age = _newest_artifact_age()
    if not have_cache:
        return True
    return age is None or age > DATA_MAX_AGE_SECONDS


def _safe_warm() -> None:
    try:
        warm()
    except Exception:  # noqa: BLE001
        logger.exception("background warm failed")


def _schedule_warm_if_stale() -> None:
    global _bg_thread
    if not _should_warm():
        return
    with _bg_lock:
        if _bg_thread is not None and _bg_thread.is_alive():
            return
        if not _should_warm():
            return
        _bg_thread = threading.Thread(target=_safe_warm, name="ldt-datastore-warm", daemon=True)
        _bg_thread.start()
        logger.info("datastore: scheduled background warm")


def ensure_warm_started() -> None:
    """Call at process start (and it's cheap to call again): kicks a
    background warm if the local artifacts are missing or stale."""
    _schedule_warm_if_stale()


def data_status() -> Dict[str, Any]:
    age = _newest_artifact_age()
    return {
        "manifest": manifest(),
        "newest_artifact_age_seconds": round(age, 1) if age is not None else None,
        "max_age_seconds": DATA_MAX_AGE_SECONDS,
        "warm_running": _warm_state["running"],
        "warm_last_ok": _warm_state["last_ok"],
        "warm_last_error": _warm_state["last_error"],
        "cache_dir": CACHE_DIR,
        "cache_dir_writable": os.access(CACHE_DIR, os.W_OK) if os.path.isdir(CACHE_DIR) else None,
        "background_warm_disabled": _BG_WARM_DISABLED,
    }


# --------------------------------------------------------------------------
# Wire the cache-backed providers into queries.py
# --------------------------------------------------------------------------
#
# This is an explicit call (made by app.py), not an import side-effect, so
# that importing ``datastore`` in a test does not silently repoint the whole
# ``queries`` module for every other test in the session.

_providers_installed = False


def install_providers() -> None:
    global _providers_installed
    if _providers_installed:
        return
    queries.set_data_providers(
        analytics=analytics_dataset,
        features=boundary_geojson,
        strategy=strategy_inventory,
    )
    _providers_installed = True
    logger.info("datastore: registered cache-backed providers with queries.py")
