"""
queries.py
================
Data access layer for the Local Development Tracker.

Every analytical dataset is read **live from Databricks Unity Catalog**
(schema ``prd_mega.sgpbpi163``) through an OAuth service principal. There is
no bundled-data fallback - if the ``DATABRICKS_*`` environment variables are
not configured this module raises ``EnvironmentError`` at import time.

Source tables
-------------
Per country (``NPL`` / ``SRB`` / ``ZMB``):

* ``GPBP_LDT_<ISO3>_admin_2``          - indicator panel, one row per
  municipality-year, raw indicator + context columns.
* ``GPBP_LDT_<ISO3>_scores_admin_2``   - 0-100 percentile score panel, one
  row per municipality-year, component + pillar score columns.
* ``ldt_boundaries_admin2_<country>``  - admin-2 geometry for the choropleth.

The Strategy Inventory page is built from the planning-documents Volume at
``LDT_DOCUMENTS_VOLUME`` (default
``/Volumes/prd_mega/sgpbpi163/vgpbpi163/LDT/Local Development Plans``).

The row -> ``analytics-data.json`` shaping mirrors, function for function,
``wb-ldt-app/scripts/lib/nepal-data.mjs`` which produced the JSON snapshots
the app used before this migration, so every downstream pure function
(score averages, province summaries, waterfalls, ...) is unchanged.

Static indicator metadata (labels, descriptions, direction, pillar, sources)
is identical across the three countries and is shipped in
``assets/data/indicator_definitions.json`` rather than a table.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

import constants

logger = logging.getLogger(__name__)

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
INDICATOR_DEFINITIONS_PATH = os.path.join(ASSETS_DIR, "data", "indicator_definitions.json")


# --------------------------------------------------------------------------
# Environment guard - fail fast, exactly like the sample Databricks project
# --------------------------------------------------------------------------

_missing_env = [k for k, v in constants.REQUIRED_DATABRICKS_ENV.items() if not v]
if _missing_env:
    raise EnvironmentError(
        "\n\nThe Local Development Tracker reads all data from Databricks Unity "
        "Catalog and has no offline fallback.\n\nMissing required environment "
        "variables:\n"
        + "\n".join(f"  {k}" for k in _missing_env)
        + "\n\nCopy .env.sample to .env and fill in:\n"
        "  DATABRICKS_SERVER_HOSTNAME=adb-xxxx.azuredatabricks.net\n"
        "  DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/abc123\n"
        "  DATABRICKS_CLIENT_ID=your-service-principal-client-id\n"
        "  DATABRICKS_CLIENT_SECRET=your-service-principal-secret\n"
    )


def credentials_provider():
    """OAuth2 service-principal credentials for the Databricks SQL connector."""
    from databricks.sdk.core import Config, oauth_service_principal

    config = Config(
        host=f"https://{constants.DATABRICKS_SERVER_HOSTNAME}",
        client_id=constants.DATABRICKS_CLIENT_ID,
        client_secret=constants.DATABRICKS_CLIENT_SECRET,
    )
    return oauth_service_principal(config)


# --------------------------------------------------------------------------
# QueryService - singleton SQL executor with an in-memory TTL cache
# (ported from the sample queries.py the user supplied)
# --------------------------------------------------------------------------

class QueryService:
    """Thread-safe data-access object with a TTL query cache."""

    _instance: Optional["QueryService"] = None
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "QueryService":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        # {sql_string: (expires_at_epoch, dataframe)}
        self._cache: Dict[str, Tuple[float, pd.DataFrame]] = {}
        self._lock = threading.Lock()

    # -- cache helpers ----------------------------------------------------

    def _cache_get(self, key: str) -> Optional[pd.DataFrame]:
        now = time.time()
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            expires_at, df = entry
            if now >= expires_at:
                del self._cache[key]
                return None
            return df

    def _cache_set(self, key: str, df: pd.DataFrame) -> None:
        expires_at = time.time() + constants.QUERY_CACHE_TTL_SECONDS
        with self._lock:
            if len(self._cache) >= constants.QUERY_CACHE_MAX_ENTRIES:
                oldest = next(iter(self._cache))
                del self._cache[oldest]
            self._cache[key] = (expires_at, df)

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()
        logger.info("Query cache cleared")

    def invalidate_query(self, query: str) -> None:
        with self._lock:
            removed = self._cache.pop(query, None) is not None
        if removed:
            logger.info("Invalidated cache for query: %s", query[:80])

    # -- executor -------------------------------------------------------

    def execute_query(self, query: str) -> pd.DataFrame:
        """Run ``query`` against Databricks SQL and return a DataFrame.

        Results are cached in memory for ``QUERY_CACHE_TTL_SECONDS`` seconds.
        """
        cached = self._cache_get(query)
        if cached is not None:
            logger.info("CACHE HIT (TTL=%ss): %s", constants.QUERY_CACHE_TTL_SECONDS, _one_line(query))
            return cached.copy(deep=True)

        from databricks import sql

        t0 = time.time()
        logger.info("Databricks query: %s", _one_line(query))
        with sql.connect(
            server_hostname=constants.DATABRICKS_SERVER_HOSTNAME,
            http_path=constants.DATABRICKS_HTTP_PATH,
            credentials_provider=credentials_provider,
        ) as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            df = pd.DataFrame(rows, columns=columns)

        logger.info(
            "Databricks query returned %d rows x %d cols in %.2fs: %s",
            len(df), len(df.columns), time.time() - t0, _one_line(query),
        )
        self._cache_set(query, df)
        return df.copy(deep=True)


def _one_line(text: str) -> str:
    return " ".join(text.split())[:160]


def execute_query(query: str) -> pd.DataFrame:
    """Module-level convenience wrapper around the singleton executor."""
    return QueryService.get_instance().execute_query(query)


def _fqtn(table: str) -> str:
    """Fully-qualified, back-tick-quoted table name."""
    return f"`{constants.LDT_CATALOG}`.`{constants.LDT_SCHEMA}`.`{table}`"


# --------------------------------------------------------------------------
# Small numeric helpers (ports of the pure functions in nepal-data.mjs /
# the previous queries.py - unchanged behaviour)
# --------------------------------------------------------------------------

def _finite(values):
    out = []
    for v in values:
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv == fv:  # not NaN
            out.append(fv)
    return out


def average(values) -> Optional[float]:
    finite = _finite(values)
    if not finite:
        return None
    return round(sum(finite) / len(finite), 2)


def normalize_land_area_km2(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if value > 100000:
        return round(value / 1_000_000, 2)
    return round(value, 2)


def _to_number(value) -> Optional[float]:
    """Port of `toNumber`: tolerant numeric parse, ``None`` on failure."""
    if value is None:
        return None
    try:
        if isinstance(value, float) and value != value:  # NaN
            return None
    except TypeError:
        pass
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _clean_label(value) -> str:
    return "" if value is None else str(value).strip()


# --------------------------------------------------------------------------
# Tolerant column resolution
# --------------------------------------------------------------------------

def _norm_col(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def _resolve_column(columns, candidates, *, table: str = "", role: str = "") -> Optional[str]:
    """Return the actual column in ``columns`` that best matches ``candidates``.

    Tries exact match, then case-/punctuation-insensitive match.
    """
    if isinstance(candidates, str):
        candidates = [candidates]
    normalized = {_norm_col(c): c for c in columns}
    for cand in candidates:
        if cand in columns:
            return cand
        hit = normalized.get(_norm_col(cand))
        if hit is not None:
            return hit
    if role:
        logger.warning(
            "%s: could not resolve %s column from candidates %s (available: %s)",
            table, role, list(candidates), list(columns),
        )
    return None


# --------------------------------------------------------------------------
# Static definitions
# --------------------------------------------------------------------------

_definitions_lock = threading.Lock()
_indicator_definitions_cache: Optional[List[Dict[str, Any]]] = None


def _indicator_definitions() -> List[Dict[str, Any]]:
    global _indicator_definitions_cache
    if _indicator_definitions_cache is None:
        with _definitions_lock:
            if _indicator_definitions_cache is None:
                with open(INDICATOR_DEFINITIONS_PATH, "r", encoding="utf-8") as fh:
                    payload = json.load(fh)
                _indicator_definitions_cache = payload["indicatorDefinitions"]
                logger.info(
                    "Loaded %d static indicator definitions from %s",
                    len(_indicator_definitions_cache), INDICATOR_DEFINITIONS_PATH,
                )
    return _indicator_definitions_cache


def _score_definitions() -> List[Dict[str, Any]]:
    result = []
    for index, item in enumerate(constants.SCORE_DEFINITIONS):
        result.append({
            "id": item["id"],
            "label": item["label"],
            "pillar": item["pillar"],
            "componentLabels": list(item["componentLabels"]),
            "sortOrder": index,
            "componentIds": [
                constants.create_score_metric_id(label) for label in item["componentLabels"]
            ],
        })
    return result


# --------------------------------------------------------------------------
# Geometry decode (WKT / WKB / GeoJSON) -> simplified GeoJSON dict
# --------------------------------------------------------------------------

def _decode_geometry(value):
    """Return a shapely geometry from a UC boundary column value, or None."""
    if value is None:
        return None
    from shapely import wkb as shp_wkb
    from shapely import wkt as shp_wkt
    from shapely.geometry import shape as shp_shape

    if isinstance(value, (bytes, bytearray, memoryview)):
        return shp_wkb.loads(bytes(value))

    text = str(value).strip()
    if not text:
        return None
    if text[0] in "{[":
        return shp_shape(json.loads(text))

    lowered = text.lower()
    if (
        len(lowered) > 16
        and len(lowered) % 2 == 0
        and all(ch in "0123456789abcdef" for ch in lowered)
    ):
        try:
            return shp_wkb.loads(bytes.fromhex(lowered))
        except Exception:  # noqa: BLE001 - fall through to WKT
            pass
    return shp_wkt.loads(text)


def _reproject(geom, source_crs: str):
    if not source_crs or source_crs.upper() in ("EPSG:4326", "4326", "WGS84"):
        return geom
    try:
        from pyproj import Transformer
        from shapely.ops import transform as shp_transform
    except ImportError:
        logger.warning(
            "Boundary CRS is %s but pyproj is not installed; leaving coordinates "
            "unprojected. `pip install pyproj` to fix.", source_crs,
        )
        return geom
    transformer = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)
    return shp_transform(lambda x, y, z=None: transformer.transform(x, y), geom)


def _geometry_to_geojson(geom, tolerance: float) -> Optional[Dict[str, Any]]:
    from shapely.geometry import mapping

    if geom is None or geom.is_empty:
        return None
    if tolerance:
        simplified = geom.simplify(tolerance, preserve_topology=True)
        if simplified is not None and not simplified.is_empty:
            geom = simplified
    return mapping(geom)


# --------------------------------------------------------------------------
# Dataset assembler (port of buildCountryAnalyticsData)
# --------------------------------------------------------------------------

_dataset_lock = threading.Lock()
_dataset_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_feature_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_strategy_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def _country_config(country_code: str) -> Dict[str, Any]:
    code = (country_code or "NPL").upper()
    if code not in constants.COUNTRY_DATA_SOURCES:
        # allow slugs too
        for c in constants.COUNTRIES:
            if c["slug"] == (country_code or "").lower():
                code = c["code"]
                break
    return constants.COUNTRY_DATA_SOURCES[code]


def _hierarchy(row: pd.Series, columns: Dict[str, str]) -> Dict[str, str]:
    municipality = _clean_label(row.get(columns["municipality"]))
    province = _clean_label(row.get(columns["province"]))
    district = _clean_label(row.get(columns["district"])) or province
    return {"municipality": municipality, "district": district, "province": province}


def _composite_key(hierarchy: Dict[str, str]) -> str:
    return "::".join([hierarchy["province"], hierarchy["district"], hierarchy["municipality"]])


def _project_municipality(
    country_code: str,
    admin_row: pd.Series,
    score_row: Optional[pd.Series],
    admin_columns: Dict[str, str],
    indicator_col_map: Dict[str, str],
    score_col_map: Dict[str, str],
    context_col_map: Dict[str, str],
    indicator_definitions: List[Dict[str, Any]],
    score_definitions: List[Dict[str, Any]],
    year_column: Optional[str],
) -> Dict[str, Any]:
    hierarchy = _hierarchy(admin_row, admin_columns)
    definitions_by_label = {d["label"]: d for d in indicator_definitions}
    pillar_labels = constants.PILLAR_SCORE_LABELS

    indicators: Dict[str, Any] = {}
    for raw_column, canonical_label in constants.ADMIN_CANONICAL_MAPPINGS.items():
        definition = definitions_by_label.get(canonical_label)
        actual = indicator_col_map.get(raw_column)
        if definition is None or actual is None:
            continue
        indicators[definition["id"]] = _to_number(admin_row.get(actual))

    score_components: Dict[str, Any] = {}
    scores: Dict[str, Any] = {}
    for raw_column, canonical_label in constants.SCORE_CANONICAL_MAPPINGS.items():
        actual = score_col_map.get(raw_column)
        value = _to_number(score_row.get(actual)) if (score_row is not None and actual) else None
        metric_id = constants.create_score_metric_id(canonical_label)
        if canonical_label in pillar_labels:
            scores[metric_id] = value
        elif canonical_label.endswith("Score"):
            score_components[metric_id] = value

    context: Dict[str, Any] = {}
    for raw_column, key in constants.CONTEXT_COLUMN_MAPPINGS.items():
        actual = context_col_map.get(raw_column)
        context[key] = _to_number(admin_row.get(actual)) if actual else None

    year_value = admin_row.get(year_column) if year_column else None
    year = int(_to_number(year_value)) if _to_number(year_value) is not None else None

    return {
        "id": constants.slugify(
            f"{country_code}-{hierarchy['province']}-{hierarchy['district']}-{hierarchy['municipality']}"
        ),
        "municipality": hierarchy["municipality"],
        "district": hierarchy["district"],
        "province": hierarchy["province"],
        "compositeKey": _composite_key(hierarchy),
        "slug": {
            "municipality": constants.slugify(hierarchy["municipality"]),
            "district": constants.slugify(hierarchy["district"]),
            "province": constants.slugify(hierarchy["province"]),
        },
        "year": year,
        "mapAvailable": False,
        "indicators": indicators,
        "scoreComponents": score_components,
        "scores": scores,
        "context": context,
    }


def _build_national_averages(municipalities, indicator_definitions, score_definitions):
    return {
        "indicators": {
            d["id"]: average([m["indicators"].get(d["id"]) for m in municipalities])
            for d in indicator_definitions
        },
        "scores": {
            d["id"]: average([m["scores"].get(d["id"]) for m in municipalities])
            for d in score_definitions
        },
    }


def _build_province_summary(municipalities, score_definitions):
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for m in municipalities:
        grouped.setdefault(m["province"], []).append(m)
    result = []
    for province, rows in grouped.items():
        result.append({
            "province": province,
            "municipalityCount": len(rows),
            "averageScores": {
                d["id"]: average([r["scores"].get(d["id"]) for r in rows])
                for d in score_definitions
            },
        })
    return sorted(result, key=lambda r: r["province"])


def _build_release(config: Dict[str, Any], year: Optional[int]) -> Dict[str, Any]:
    return {
        "key": f"{config['release_key_prefix']}-{year}-v1",
        "year": year,
        "adminTable": config["admin_table"],
        "scoreTable": config["scores_table"],
        "boundaryTable": config["boundary_table"],
        "catalog": constants.LDT_CATALOG,
        "schema": constants.LDT_SCHEMA,
    }


def _assemble_dataset(country_code: str) -> Dict[str, Any]:
    config = _country_config(country_code)
    code = country_code.upper()
    admin_columns = config["admin_columns"]

    admin_fqtn = _fqtn(config["admin_table"])
    scores_fqtn = _fqtn(config["scores_table"])

    logger.info(
        "Assembling %s analytics dataset from %s.%s (%s + %s)",
        code, constants.LDT_CATALOG, constants.LDT_SCHEMA,
        config["admin_table"], config["scores_table"],
    )

    admin_df = execute_query(f"SELECT * FROM {admin_fqtn}")
    scores_df = execute_query(f"SELECT * FROM {scores_fqtn}")

    if admin_df.empty:
        raise RuntimeError(f"{admin_fqtn} returned no rows - cannot build {code} dataset")

    admin_cols = list(admin_df.columns)
    score_cols = list(scores_df.columns)

    year_column = _resolve_column(
        admin_cols, config["year_column_candidates"], table=config["admin_table"], role="year"
    )
    score_year_column = _resolve_column(
        score_cols, config["year_column_candidates"], table=config["scores_table"], role="year"
    )

    # Resolve every raw source column once, tolerantly.
    indicator_col_map = {
        raw: _resolve_column(admin_cols, [raw])
        for raw in constants.ADMIN_CANONICAL_MAPPINGS
    }
    context_col_map = {
        raw: _resolve_column(admin_cols, [raw])
        for raw in constants.CONTEXT_COLUMN_MAPPINGS
    }
    score_col_map = {
        raw: _resolve_column(score_cols, [raw])
        for raw in constants.SCORE_CANONICAL_MAPPINGS
    }
    _log_unresolved(config["admin_table"], "indicator", indicator_col_map)
    _log_unresolved(config["admin_table"], "context", context_col_map)
    _log_unresolved(config["scores_table"], "score", score_col_map)

    admin_hierarchy_cols = {
        role: _resolve_column(admin_cols, [name], table=config["admin_table"], role=f"admin.{role}") or name
        for role, name in admin_columns.items()
    }
    score_hierarchy_cols = {
        role: _resolve_column(score_cols, [name], table=config["scores_table"], role=f"scores.{role}") or name
        for role, name in admin_columns.items()
    }

    indicator_definitions = _indicator_definitions()
    score_definitions = _score_definitions()

    # Score lookup keyed by "Year::Province::District::Municipality".
    score_lookup: Dict[str, pd.Series] = {}
    for _, row in scores_df.iterrows():
        hierarchy = _hierarchy(row, score_hierarchy_cols)
        year_val = _to_number(row.get(score_year_column)) if score_year_column else None
        year_token = str(int(year_val)) if year_val is not None else ""
        score_lookup[f"{year_token}::{_composite_key(hierarchy)}"] = row

    municipalities = []
    for _, admin_row in admin_df.iterrows():
        hierarchy = _hierarchy(admin_row, admin_hierarchy_cols)
        year_val = _to_number(admin_row.get(year_column)) if year_column else None
        year_token = str(int(year_val)) if year_val is not None else ""
        score_row = score_lookup.get(f"{year_token}::{_composite_key(hierarchy)}")
        municipalities.append(
            _project_municipality(
                code, admin_row, score_row, admin_hierarchy_cols,
                indicator_col_map, score_col_map, context_col_map,
                indicator_definitions, score_definitions, year_column,
            )
        )

    years = sorted({m["year"] for m in municipalities if m["year"] is not None})
    latest_year = years[-1] if years else None
    latest = [m for m in municipalities if m["year"] == latest_year] or municipalities

    national_averages = _build_national_averages(municipalities, indicator_definitions, score_definitions)
    province_summary = _build_province_summary(latest, score_definitions)

    metrics = [
        {"id": d["id"], "label": d["label"], "kind": "score", "pillar": d["pillar"]}
        for d in score_definitions
    ] + [
        {
            "id": d["id"], "label": d["label"], "kind": "indicator",
            "pillar": d.get("pillar"), "higherIsBetter": d.get("higherIsBetter"),
        }
        for d in indicator_definitions
    ]

    dataset = {
        "generatedAt": pd.Timestamp.utcnow().isoformat(),
        "release": _build_release(config, latest_year),
        "coverage": {
            "analyticsMunicipalityCount": len(latest),
            "mapMunicipalityCount": 0,  # filled lazily by load_map_feature_collection
            "analyticsOnlyCount": 0,
            "boundaryOnlyCount": 0,
        },
        "metricIds": {
            "defaultMapMetricId": constants.DEFAULT_MAP_METRIC_ID,
            "defaultScatterXMetricId": constants.DEFAULT_SCATTER_X_METRIC_ID,
            "defaultScatterYMetricId": constants.DEFAULT_SCATTER_Y_METRIC_ID,
        },
        "provinces": sorted({m["province"] for m in municipalities if m["province"]}),
        "years": years,
        "indicatorDefinitions": indicator_definitions,
        "scoreDefinitions": score_definitions,
        "metrics": metrics,
        "nationalAverages": national_averages,
        "provinceSummary": province_summary,
        "municipalities": municipalities,
        "mapFeatureKeys": [],
    }
    logger.info(
        "%s dataset assembled: %d municipality-year rows, %d in latest year %s, %d provinces, years=%s",
        code, len(municipalities), len(latest), latest_year, len(dataset["provinces"]), years,
    )
    return dataset


def _log_unresolved(table: str, role: str, col_map: Dict[str, Optional[str]]) -> None:
    unresolved = [raw for raw, actual in col_map.items() if actual is None]
    if unresolved:
        logger.warning("%s: %d %s columns not found: %s", table, len(unresolved), role, unresolved)


# --------------------------------------------------------------------------
# Boundary features (port of buildCountryMatchedGeojson)
# --------------------------------------------------------------------------

def _assemble_feature_collection(country_code: str) -> Dict[str, Any]:
    config = _country_config(country_code)
    code = country_code.upper()
    table = config["boundary_table"]
    fqtn = _fqtn(table)

    logger.info(
        "Fetching %s admin-2 boundaries from %s.%s.%s",
        code, constants.LDT_CATALOG, constants.LDT_SCHEMA, table,
    )
    df = execute_query(f"SELECT * FROM {fqtn}")
    if df.empty:
        logger.warning("%s returned no rows - the %s map will be empty", fqtn, code)
        return {"type": "FeatureCollection", "features": []}

    columns = list(df.columns)
    muni_col = _resolve_column(columns, config["boundary_municipality_candidates"], table=table, role="boundary.municipality")
    dist_col = _resolve_column(columns, config["boundary_district_candidates"], table=table, role="boundary.district")
    prov_col = _resolve_column(columns, config["boundary_province_candidates"], table=table, role="boundary.province")
    geom_col = _resolve_column(columns, config["geometry_column_candidates"], table=table, role="geometry")

    if not (muni_col and prov_col and geom_col):
        raise RuntimeError(
            f"{fqtn}: could not resolve boundary columns "
            f"(municipality={muni_col}, district={dist_col}, province={prov_col}, geometry={geom_col}). "
            f"Available columns: {columns}. Adjust COUNTRY_DATA_SOURCES['{code}'] in constants.py."
        )
    logger.info(
        "%s boundary columns resolved: municipality=%s district=%s province=%s geometry=%s",
        code, muni_col, dist_col, prov_col, geom_col,
    )

    boundary_columns = {
        "municipality": muni_col,
        "district": dist_col or prov_col,
        "province": prov_col,
    }
    tolerance = config.get("simplify_tolerance", 0.0)
    crs = config.get("boundary_crs", "EPSG:4326")

    grouped: Dict[str, Dict[str, Any]] = {}
    decode_failures = 0
    for _, row in df.iterrows():
        hierarchy = _hierarchy(row, boundary_columns)
        key = _composite_key(hierarchy)
        try:
            geom = _decode_geometry(row.get(geom_col))
        except Exception:  # noqa: BLE001
            decode_failures += 1
            continue
        if geom is None or geom.is_empty:
            continue
        geom = _reproject(geom, crs)
        entry = grouped.setdefault(key, {"hierarchy": hierarchy, "geoms": []})
        entry["geoms"].append(geom)

    if decode_failures:
        logger.warning("%s: %d boundary rows failed geometry decode", code, decode_failures)

    from shapely.ops import unary_union

    features = []
    for key, entry in grouped.items():
        geoms = entry["geoms"]
        merged = geoms[0] if len(geoms) == 1 else unary_union(geoms)
        geojson_geom = _geometry_to_geojson(merged, tolerance)
        if geojson_geom is None:
            continue
        h = entry["hierarchy"]
        features.append({
            "type": "Feature",
            "properties": {
                "Municipality": h["municipality"],
                "District": h["district"],
                "Province": h["province"],
                "compositeKey": key,
            },
            "geometry": geojson_geom,
        })

    logger.info("%s boundary feature collection built: %d features", code, len(features))
    return {"type": "FeatureCollection", "features": features}


# --------------------------------------------------------------------------
# Cached public accessors
# --------------------------------------------------------------------------

def _cached(cache: Dict[str, Tuple[float, Any]], key: str, builder):
    now = time.time()
    with _dataset_lock:
        entry = cache.get(key)
        if entry and now < entry[0]:
            return entry[1]
    value = builder(key)
    with _dataset_lock:
        cache[key] = (time.time() + constants.QUERY_CACHE_TTL_SECONDS, value)
    return value


def get_analytics_dataset(country_code: str) -> Dict[str, Any]:
    """Return the fully-assembled analytics dataset for a country (cached)."""
    return _cached(_dataset_cache, country_code.upper(), _assemble_dataset)


def load_map_feature_collection(country_code: str) -> Dict[str, Any]:
    """Return the admin-2 boundary GeoJSON FeatureCollection for a country."""
    fc = _cached(_feature_cache, country_code.upper(), _assemble_feature_collection)
    # Backfill map coverage onto the (separately cached) dataset.
    dataset = _dataset_cache.get(country_code.upper())
    if dataset:
        keys = {f["properties"]["compositeKey"] for f in fc.get("features", [])}
        analytics_keys = {m["compositeKey"] for m in dataset[1]["municipalities"]}
        matched = keys & analytics_keys
        dataset[1]["coverage"]["mapMunicipalityCount"] = len(matched)
        dataset[1]["coverage"]["boundaryOnlyCount"] = len(keys - analytics_keys)
        dataset[1]["mapFeatureKeys"] = sorted(matched)
        for m in dataset[1]["municipalities"]:
            m["mapAvailable"] = m["compositeKey"] in matched
    return fc


def clear_caches() -> None:
    with _dataset_lock:
        _dataset_cache.clear()
        _feature_cache.clear()
        _strategy_cache.clear()
    QueryService.get_instance().clear_cache()
    logger.info("All LDT caches cleared")


# --------------------------------------------------------------------------
# Derived accessors (unchanged ports)
# --------------------------------------------------------------------------

def get_years(country_code: str) -> List[int]:
    return get_analytics_dataset(country_code).get("years", [])


def get_provinces(country_code: str) -> List[str]:
    provinces = get_analytics_dataset(country_code).get("provinces", [])
    return ["all"] + list(provinces)


def get_municipalities_for_year(country_code: str, year: int) -> List[Dict[str, Any]]:
    dataset = get_analytics_dataset(country_code)
    rows = [m for m in dataset["municipalities"] if m["year"] == year]
    return rows or dataset["municipalities"]


def get_municipality_options(country_code: str, year: int, province: str = "all") -> List[Dict[str, str]]:
    rows = get_municipalities_for_year(country_code, year)
    if province != "all":
        rows = [m for m in rows if m["province"] == province]
    options = [
        {"id": m["id"], "label": f"{m['municipality']}, {m['district']}"} for m in rows
    ]
    return sorted(options, key=lambda o: o["label"])


def find_municipality(country_code: str, year: int, municipality_id: str) -> Optional[Dict[str, Any]]:
    rows = get_municipalities_for_year(country_code, year)
    for m in rows:
        if m["id"] == municipality_id or m["compositeKey"] == municipality_id:
            return m
    return rows[0] if rows else None


def get_metrics(country_code: str) -> List[Dict[str, Any]]:
    return get_analytics_dataset(country_code).get("metrics", [])


def get_score_metrics(country_code: str) -> List[Dict[str, Any]]:
    return [m for m in get_metrics(country_code) if m["kind"] == "score"]


def get_score_definitions(country_code: str) -> List[Dict[str, Any]]:
    return get_analytics_dataset(country_code).get("scoreDefinitions", [])


def get_indicator_definitions(country_code: str) -> List[Dict[str, Any]]:
    return get_analytics_dataset(country_code).get("indicatorDefinitions", [])


def find_metric_by_id(metrics: List[Dict[str, Any]], metric_id: str, fallback_id: str) -> Dict[str, Any]:
    for m in metrics:
        if m["id"] == metric_id:
            return m
    for m in metrics:
        if m["id"] == fallback_id:
            return m
    return metrics[0]


def get_metric_value(municipality: Dict[str, Any], metric: Dict[str, Any]) -> Optional[float]:
    if metric["kind"] == "score":
        return municipality.get("scores", {}).get(metric["id"])
    return municipality.get("indicators", {}).get(metric["id"])


def build_metric_summary(municipalities: List[Dict[str, Any]], metric: Dict[str, Any]) -> Dict[str, Optional[float]]:
    values = _finite([get_metric_value(m, metric) for m in municipalities])
    return {
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
        "average": average(values),
    }


def build_national_component_averages(municipalities: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    component_ids = set()
    for m in municipalities:
        component_ids.update(m.get("scoreComponents", {}).keys())
    return {
        cid: average([m.get("scoreComponents", {}).get(cid) for m in municipalities])
        for cid in component_ids
    }


def build_province_summary(country_code: str, municipalities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    score_defs = get_score_definitions(country_code)
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for m in municipalities:
        grouped.setdefault(m["province"], []).append(m)

    result = []
    for province, rows in grouped.items():
        avg_scores = {
            d["id"]: average([r["scores"].get(d["id"]) for r in rows]) for d in score_defs
        }
        result.append({
            "province": province,
            "municipalityCount": len(rows),
            "averageScores": avg_scores,
        })
    return sorted(result, key=lambda r: r["province"])


def infer_score_definition(score_definitions: List[Dict[str, Any]], metric: Dict[str, Any]) -> Dict[str, Any]:
    if metric["kind"] == "score":
        for d in score_definitions:
            if d["id"] == metric["id"]:
                return d
        return score_definitions[0]
    pillar = metric.get("pillar")
    if pillar:
        for d in score_definitions:
            if d["pillar"] == pillar:
                return d
    return score_definitions[0]


def build_score_waterfalls(
    country_code: str,
    selected_municipality: Dict[str, Any],
    municipalities_for_year: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    score_definitions = get_score_definitions(country_code)
    indicator_definitions = get_indicator_definitions(country_code)
    indicator_by_id = {d["id"]: d for d in indicator_definitions}
    national_component_averages = build_national_component_averages(municipalities_for_year)

    national_score_averages = {
        d["id"]: average([m["scores"].get(d["id"]) for m in municipalities_for_year])
        for d in score_definitions
    }

    waterfalls = []
    for definition in score_definitions:
        valid_count = max(
            sum(
                1
                for cid in definition["componentIds"]
                if selected_municipality["scoreComponents"].get(cid) is not None
                and national_component_averages.get(cid) is not None
            ),
            1,
        )

        rows = []
        for index, component_id in enumerate(definition["componentIds"]):
            municipality_value = selected_municipality["scoreComponents"].get(component_id)
            national_value = national_component_averages.get(component_id)
            delta = None
            if municipality_value is not None and national_value is not None:
                delta = municipality_value - national_value
            label = (
                definition["componentLabels"][index]
                if index < len(definition["componentLabels"])
                else component_id
            )
            rows.append({
                "componentId": component_id,
                "label": label,
                "description": None,
                "municipalityValue": municipality_value,
                "nationalValue": national_value,
                "contribution": round(delta / valid_count, 2) if delta is not None else None,
            })

        municipality_score = selected_municipality["scores"].get(definition["id"])
        national_score = national_score_averages.get(definition["id"])
        total_difference = None
        if municipality_score is not None and national_score is not None:
            total_difference = round(municipality_score - national_score, 2)

        waterfalls.append({
            "scoreId": definition["id"],
            "scoreLabel": definition["label"],
            "municipalityScore": municipality_score,
            "nationalScore": national_score,
            "totalDifference": total_difference,
            "rows": rows,
        })

    return waterfalls


def get_analytics_page_data(
    country_code: str,
    year: Optional[int] = None,
    province: str = "all",
    municipality_id: Optional[str] = None,
    metric_id: Optional[str] = None,
    x_metric_id: Optional[str] = None,
    y_metric_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Single dict bundling everything the analytics page needs."""
    dataset = get_analytics_dataset(country_code)
    country = constants.COUNTRY_BY_CODE.get(country_code, constants.DEFAULT_COUNTRY)

    years = dataset["years"]
    selected_year = year if year in years else years[-1]

    municipalities_for_year = get_municipalities_for_year(country_code, selected_year)
    provinces = ["all"] + sorted({m["province"] for m in municipalities_for_year})
    selected_province = province if province in provinces else "all"

    province_filtered = (
        municipalities_for_year
        if selected_province == "all"
        else [m for m in municipalities_for_year if m["province"] == selected_province]
    )

    metrics = dataset["metrics"]
    score_metrics = [m for m in metrics if m["kind"] == "score"]

    selected_metric = find_metric_by_id(metrics, metric_id or constants.DEFAULT_MAP_METRIC_ID, constants.DEFAULT_MAP_METRIC_ID)
    selected_x_metric = find_metric_by_id(score_metrics, x_metric_id or constants.DEFAULT_SCATTER_X_METRIC_ID, constants.DEFAULT_SCATTER_X_METRIC_ID)
    selected_y_metric = find_metric_by_id(score_metrics, y_metric_id or constants.DEFAULT_SCATTER_Y_METRIC_ID, constants.DEFAULT_SCATTER_Y_METRIC_ID)

    municipality_options = [
        {"id": m["id"], "label": f"{m['municipality']}, {m['district']}"} for m in province_filtered
    ]
    municipality_options.sort(key=lambda o: o["label"])

    fallback_id = municipality_options[0]["id"] if municipality_options else (
        municipalities_for_year[0]["id"] if municipalities_for_year else None
    )
    selected_municipality = find_municipality(country_code, selected_year, municipality_id or fallback_id)
    if selected_municipality is None:
        selected_municipality = municipalities_for_year[0]

    # Map features
    feature_collection = load_map_feature_collection(country_code)
    by_composite_key = {m["compositeKey"]: m for m in municipalities_for_year}
    map_features = []
    mapped_keys = set()
    for feature in feature_collection.get("features", []):
        composite_key = feature["properties"].get("compositeKey")
        municipality = by_composite_key.get(composite_key)
        if municipality is None:
            continue
        mapped_keys.add(composite_key)
        if selected_province != "all" and feature["properties"].get("Province") != selected_province:
            continue
        value = get_metric_value(municipality, selected_metric)
        map_features.append({
            "type": feature["type"],
            "properties": feature["properties"],
            "geometry": feature["geometry"],
            "metricValue": value,
        })

    metric_summary = build_metric_summary(province_filtered, selected_metric)

    score_definitions = get_score_definitions(country_code)
    indicator_definitions = get_indicator_definitions(country_code)
    indicator_by_id = {d["id"]: d for d in indicator_definitions}
    selected_score_definition = infer_score_definition(score_definitions, selected_metric)
    national_component_averages = build_national_component_averages(municipalities_for_year)

    score_component_definitions = []
    score_driver_rows = []
    for index, component_id in enumerate(selected_score_definition["componentIds"]):
        label = (
            selected_score_definition["componentLabels"][index]
            if index < len(selected_score_definition["componentLabels"])
            else component_id
        )
        score_component_definitions.append({"id": component_id, "label": label, "description": None})
        municipality_value = selected_municipality["scoreComponents"].get(component_id)
        national_value = national_component_averages.get(component_id)
        delta = None
        if municipality_value is not None and national_value is not None:
            delta = round(municipality_value - national_value, 2)
        score_driver_rows.append({
            "componentId": component_id,
            "label": label,
            "municipalityValue": municipality_value,
            "nationalValue": national_value,
            "delta": delta,
        })

    waterfalls = build_score_waterfalls(country_code, selected_municipality, municipalities_for_year)
    province_summary = build_province_summary(country_code, municipalities_for_year)

    scatter2d_points = []
    for m in province_filtered:
        scatter2d_points.append({
            "id": m["id"],
            "label": m["municipality"],
            "district": m["district"],
            "province": m["province"],
            "x": m["scores"].get(selected_x_metric["id"]),
            "y": m["scores"].get(selected_y_metric["id"]),
            "selected": m["id"] == selected_municipality["id"],
        })

    scatter3d_points = []
    for m in province_filtered:
        scatter3d_points.append({
            "id": m["id"],
            "label": m["municipality"],
            "district": m["district"],
            "province": m["province"],
            "x": m["scores"].get("prosperity_score"),
            "y": m["scores"].get("infrastructure_score"),
            "z": m["scores"].get("livability_score"),
            "selected": m["id"] == selected_municipality["id"],
        })

    coverage = dict(dataset.get("coverage", {}))
    coverage["mapMunicipalityCount"] = len(mapped_keys)

    return {
        "country": {"code": country["code"], "slug": country["slug"], "name": country["name"]},
        "release": dataset.get("release", {}),
        "filters": {
            "years": years,
            "provinces": provinces,
            "metrics": metrics,
            "scoreMetrics": score_metrics,
            "municipalities": municipality_options,
        },
        "coverage": coverage,
        "selected": {
            "year": selected_year,
            "province": selected_province,
            "municipalityId": selected_municipality["id"],
            "municipalityName": selected_municipality["municipality"],
            "metricId": selected_metric["id"],
            "xMetricId": selected_x_metric["id"],
            "yMetricId": selected_y_metric["id"],
        },
        "municipality": selected_municipality,
        "map": {
            "metric": selected_metric,
            "features": map_features,
            "summary": metric_summary,
            "coverageLabel": f"{len(mapped_keys)} mapped of {len(municipalities_for_year)} analytics municipalities",
        },
        "scatter2d": {"xMetric": selected_x_metric, "yMetric": selected_y_metric, "points": scatter2d_points},
        "scatter3d": {"points": scatter3d_points},
        "metadata": {
            "selectedMetric": indicator_by_id.get(selected_metric["id"]),
            "scoreDefinition": selected_score_definition,
            "scoreComponents": score_component_definitions,
            "scoreDriverRows": score_driver_rows,
        },
        "waterfalls": waterfalls,
        "provinceSummary": province_summary,
    }


def get_methodology_data(country_code: str = None) -> Dict[str, Any]:
    country_code = country_code or constants.DEFAULT_COUNTRY["code"]
    dataset = get_analytics_dataset(country_code)
    return {
        "indicatorDefinitions": dataset.get("indicatorDefinitions", []),
        "scoreDefinitions": dataset.get("scoreDefinitions", []),
        "metrics": dataset.get("metrics", []),
        "coverage": dataset.get("coverage", {}),
    }


# --------------------------------------------------------------------------
# Country landing-page dataset
# --------------------------------------------------------------------------

def load_country_dataset(country_code: str) -> Dict[str, Any]:
    return get_analytics_dataset(country_code)


def sum_finite(values) -> float:
    return sum(_finite(values))


def build_country_home_model(country: Dict[str, Any], dataset: Dict[str, Any]) -> Dict[str, Any]:
    """Port of `buildCountryHomeModel` from country-home.ts."""
    release_year = dataset.get("release", {}).get("year", 0) or 0
    years = dataset.get("years", [release_year]) or [release_year]
    latest_year = max([release_year] + list(years))

    rows = [m for m in dataset["municipalities"] if m["year"] == latest_year]
    if not rows:
        rows = dataset["municipalities"]

    total_population = sum_finite([m["context"].get("population") for m in rows])
    total_area = sum_finite([m["context"].get("totalLandAreaKm2") for m in rows])

    population_millions = country["profile"]["population_millions"]
    if population_millions is None:
        population_millions = total_population / 1_000_000
    area_km2 = country["profile"]["area_km2"]
    if area_km2 is None:
        area_km2 = total_area

    grouped: Dict[str, List[str]] = {}
    for m in rows:
        grouped.setdefault(m["province"], []).append(m["municipality"])

    groups = [
        {"name": name, "lowerUnits": sorted(units)}
        for name, units in grouped.items()
    ]
    groups.sort(key=lambda g: g["name"])

    return {
        "latestYear": latest_year,
        "releaseKey": dataset.get("release", {}).get("key", ""),
        "lowerCount": len(rows),
        "higherCount": len(groups),
        "populationLabel": f"{population_millions:.1f} million",
        "areaLabel": f"{area_km2:,.1f} sq km",
        "groups": groups,
    }


def get_country_landing_actions(country: Dict[str, Any]) -> List[Dict[str, str]]:
    lower_unit_label = country["admin_labels"]["lower"]["singular"]
    lower_unit_label = lower_unit_label[0].lower() + lower_unit_label[1:]

    actions = [
        {
            "label": f"Analyze {lower_unit_label} metrics",
            "href": f"?page={country['slug']}&view=analytics",
            "variant": "primary",
            "align": "left",
        }
    ]

    if country["slug"] in constants.STRATEGY_INVENTORY_SLUGS:
        actions.append({
            "label": "Strategy inventory",
            "href": f"?page={country['slug']}&view=strategy-inventory",
            "variant": "secondary",
            "align": "left",
        })

    actions.append({
        "label": "Return to Homepage",
        "href": "?page=home",
        "variant": "secondary",
        "align": "right",
    })

    return actions


def get_plan_availability_disclosure(country: Dict[str, Any]) -> Dict[str, str]:
    plan_level = country["planning_documents"]["plan_source_admin_level"]
    if plan_level == "lower":
        label = country["admin_labels"]["lower"]["plural"]
    else:
        label = country["admin_labels"]["higher"]["plural"]
    tracked_unit_label = label[0].lower() + label[1:]

    return {
        "trackedUnitLabel": tracked_unit_label,
        "description": (
            f"{country['planning_documents']['message']} This section tracks "
            f"which {tracked_unit_label} currently have local/SNG plan links "
            f"available for AI-assisted analysis."
        ),
    }


# --------------------------------------------------------------------------
# Strategy inventory - built from the planning-documents Volume
# --------------------------------------------------------------------------

_DOC_TYPE_KEYWORDS = {
    "strategy": ("strategy", "strategij", "strateg", "development plan", "ldp", "plan of development"),
    "budget": ("budget", "budzet", "buxhet", "financ"),
    "plan": ("plan", "programme", "program"),
}
_LANGUAGE_TOKENS = {
    "en": {"en", "eng", "english"},
    "sr": {"sr", "srp", "srb", "serbian", "srpski", "lat", "cyr"},
    "ne": {"ne", "np", "npl", "nep", "nepali"},
}


def _workspace_client():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient(
        host=f"https://{constants.DATABRICKS_SERVER_HOSTNAME}",
        client_id=constants.DATABRICKS_CLIENT_ID,
        client_secret=constants.DATABRICKS_CLIENT_SECRET,
    )


def _list_volume_tree(root: str, max_depth: int = 4) -> List[Dict[str, Any]]:
    """Flat list of files under ``root``: [{path, name, parent, size}]."""
    client = _workspace_client()
    files: List[Dict[str, Any]] = []

    def _walk(path: str, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = list(client.files.list_directory_contents(path))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cannot list volume path %s: %s", path, exc)
            return
        for entry in entries:
            entry_path = (entry.path or "").rstrip("/")
            name = entry_path.split("/")[-1]
            if entry.is_directory:
                _walk(entry_path, depth + 1)
            else:
                files.append({
                    "path": entry_path,
                    "name": name,
                    "parent": entry_path.rsplit("/", 1)[0].split("/")[-1],
                    "size": getattr(entry, "file_size", None),
                })

    _walk(root.rstrip("/"), 0)
    return files


def _classify_document(name: str) -> Dict[str, Any]:
    lowered = name.lower()
    doc_type = "other"
    for candidate, keywords in _DOC_TYPE_KEYWORDS.items():
        if any(k in lowered for k in keywords):
            doc_type = candidate
            break

    years = [int(y) for y in re.findall(r"(?:19|20)\d{2}", name)]
    publication_year = max(years) if years else None

    stem = lowered.rsplit(".", 1)[0] if "." in lowered else lowered
    tokens = set(re.split(r"[^a-z0-9]+", stem))
    language = "unknown"
    for lang, markers in _LANGUAGE_TOKENS.items():
        if tokens & markers:
            language = lang
            break

    ext = lowered.rsplit(".", 1)[-1] if "." in lowered else ""
    parsing_status = "parsed" if ext in ("pdf", "docx", "doc", "txt", "md") else "needs_review"

    return {
        "document_type": doc_type,
        "publication_year": publication_year,
        "language": language,
        "parsing_status": parsing_status,
        "file_extension": ext,
    }


def _build_strategy_inventory(country_code: str) -> Optional[Dict[str, Any]]:
    country = constants.COUNTRY_BY_CODE.get(country_code)
    if not country or country["slug"] not in constants.STRATEGY_INVENTORY_SLUGS:
        return None

    config = _country_config(country_code)
    subdir = config.get("documents_subdir", country["name"])
    root = f"{constants.LDT_DOCUMENTS_VOLUME.rstrip('/')}/{subdir}"

    logger.info("Building %s strategy inventory from volume %s", country_code, root)
    files = _list_volume_tree(root)
    logger.info("%s strategy inventory: %d document files found under %s", country_code, len(files), root)

    records: List[Dict[str, Any]] = []
    for f in files:
        if f["name"].startswith(".") or f["size"] in (0, None) and f["name"].lower() in ("readme", "readme.md"):
            continue
        meta = _classify_document(f["name"])
        lsg_name = f["parent"] or country["name"]
        records.append({
            "country_code": country_code,
            "lsg_id": constants.slugify(f"{country_code}-{lsg_name}"),
            "lsg_name": lsg_name,
            "region_name": "",
            "document_type": meta["document_type"],
            "document_title": os.path.splitext(f["name"])[0],
            "publication_year": meta["publication_year"],
            "source_url": f["path"],
            "source_status": "found",
            "language": meta["language"],
            "translation_status": "unknown",
            "parsing_status": meta["parsing_status"],
            "ai_ready": meta["parsing_status"] == "parsed",
            "notes": None,
            "last_updated": None,
        })

    expected = config.get("expected_lsg_count") or len({r["lsg_name"] for r in records}) or 1
    return {
        "country_code": country_code,
        "country_name": country["name"],
        "is_sample_data": False,
        "expected_lsg_count": expected,
        "last_updated": None,
        "summary_override": None,
        "records": records,
    }


def get_strategy_inventory_dataset(country_code: str) -> Optional[Dict[str, Any]]:
    """Load the strategy inventory for a country from the documents Volume."""
    country = constants.COUNTRY_BY_CODE.get(country_code)
    if not country or country["slug"] not in constants.STRATEGY_INVENTORY_SLUGS:
        return None
    return _cached(_strategy_cache, country_code.upper(), lambda _k: _build_strategy_inventory(country_code))


def get_readiness_category(record: Dict[str, Any]) -> str:
    """Port of `getReadinessCategory` from strategy-inventory/summarize.ts."""
    source_status = record.get("source_status")
    if source_status in ("missing", "not_available"):
        return "Missing"

    parsing_status = record.get("parsing_status")
    if source_status == "needs_validation" or parsing_status in ("failed", "needs_review"):
        return "Needs Validation"

    is_serbian_exception = record.get("country_code") == "SRB" and record.get("language") == "sr"
    is_ai_ready = (
        source_status == "found"
        and parsing_status == "parsed"
        and (record.get("ai_ready") or is_serbian_exception)
    )
    if is_ai_ready:
        return "AI-ready"

    translation_status = record.get("translation_status")
    needs_translation = not is_serbian_exception and translation_status in ("needs_translation", "partial")
    if needs_translation:
        return "Needs Translation"

    return "Found / Not Parsed"


def get_strategy_inventory_summary(
    records: List[Dict[str, Any]], expected_lsgs: int, summary_override: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Port of `getStrategyInventoryDisplaySummary`."""

    def has_document_source(record):
        return record.get("source_status") in ("found", "needs_validation")

    def lsg_key(record):
        return (record.get("lsg_id") or record.get("lsg_name") or "").strip().lower()

    document_records = [r for r in records if has_document_source(r)]
    covered_keys = {lsg_key(r) for r in document_records}

    missing_records = [r for r in records if not has_document_source(r)]
    seen = set()
    missing_lsgs = []
    for r in missing_records:
        key = lsg_key(r)
        if key in seen:
            continue
        seen.add(key)
        missing_lsgs.append({"lsg_id": r.get("lsg_id"), "lsg_name": r.get("lsg_name"), "region_name": r.get("region_name")})

    publication_year_counts: Dict[str, int] = {}
    for r in document_records:
        year = str(r["publication_year"]) if r.get("publication_year") else "Unknown"
        publication_year_counts[year] = publication_year_counts.get(year, 0) + 1

    status_counts = {c: 0 for c in constants.READINESS_CATEGORIES}
    for r in records:
        category = get_readiness_category(r)
        status_counts[category] = status_counts.get(category, 0) + 1

    total_missing = max(status_counts.get("Missing", 0), len(missing_lsgs))
    status_counts["Missing"] = total_missing

    summary = {
        "expected_lsgs": expected_lsgs,
        "lsgs_with_any_document": len(covered_keys),
        "coverage_rate": (len(covered_keys) / expected_lsgs) if expected_lsgs else 0,
        "total_documents_found": len(document_records),
        "strategies_found": len([r for r in document_records if r.get("document_type") == "strategy"]),
        "budgets_found": len([r for r in document_records if r.get("document_type") == "budget"]),
        "ai_ready_documents": len([r for r in records if get_readiness_category(r) == "AI-ready"]),
        "needs_translation": len([r for r in records if get_readiness_category(r) == "Needs Translation"]),
        "needs_validation": len([r for r in records if get_readiness_category(r) == "Needs Validation"]),
        "missing_lsgs": missing_lsgs,
        "publication_year_counts": sorted(
            [{"year": y, "count": c} for y, c in publication_year_counts.items()],
            key=lambda row: (row["year"] == "Unknown", row["year"]),
        ),
        "status_breakdown": [{"category": c, "count": status_counts[c]} for c in constants.READINESS_CATEGORIES],
        "latest_last_updated": max((r.get("last_updated") or "" for r in records), default=None) or None,
    }

    if summary_override:
        summary.update({k: v for k, v in summary_override.items() if v is not None})

    return summary
