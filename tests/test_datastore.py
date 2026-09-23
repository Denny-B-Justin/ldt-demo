"""datastore: artifact resolution, warm(), and request-safe accessors."""

from __future__ import annotations

import json
import os

import pytest

import constants
import datastore
import queries


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """Point datastore at empty cache/snapshot dirs and restore queries'
    providers afterwards so other tests are unaffected."""
    monkeypatch.setattr(datastore, "CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(datastore, "SNAPSHOT_DIR", str(tmp_path / "snapshot"))
    monkeypatch.setattr(datastore, "_BG_WARM_DISABLED", True)
    with datastore._MEMO_LOCK:
        datastore._MEMO.clear()
    saved = (queries._ANALYTICS_PROVIDER, queries._FEATURE_PROVIDER, queries._STRATEGY_PROVIDER)
    yield tmp_path
    queries._ANALYTICS_PROVIDER, queries._FEATURE_PROVIDER, queries._STRATEGY_PROVIDER = saved
    with datastore._MEMO_LOCK:
        datastore._MEMO.clear()


def test_falls_back_to_bundled_data_when_no_artifacts(isolated_cache):
    ds = datastore.analytics_dataset("ZMB")
    assert ds["municipalities"], "expected bundled Zambia dataset to load"
    # bundled fallback is the committed assets/data/zambia/analytics-data.json
    assert ds["release"]["year"]


def test_home_summary_is_cheap_and_shaped(isolated_cache):
    summary = datastore.home_summary()
    assert summary["countryWorkspaces"] == len(constants.COUNTRIES)
    assert summary["latestYear"]


@pytest.fixture
def zmb_only(monkeypatch):
    """The shared fake executor only knows the Zambia tables, so restrict
    warm() to Zambia for tests that exercise the live assembler. Also stub the
    documents-Volume walk (network) that the strategy inventory would do."""
    zmb = [c for c in constants.COUNTRIES if c["code"] == "ZMB"]
    monkeypatch.setattr(constants, "COUNTRIES", zmb)
    monkeypatch.setattr(queries, "_list_volume_tree", lambda *a, **k: [])


def test_warm_writes_gzip_artifacts_and_manifest(isolated_cache, zmb_only):
    datastore.warm(force=True)
    cache_dir = datastore.CACHE_DIR
    assert os.path.exists(os.path.join(cache_dir, datastore._analytics_name("ZMB")))
    assert os.path.exists(os.path.join(cache_dir, datastore._boundary_name("ZMB")))
    man = json.load(open(os.path.join(cache_dir, "manifest.json")))
    assert man["countries"] == ["ZMB"]

    # a subsequent read now comes from the freshly written cache artifact
    ds = datastore.analytics_dataset("ZMB")
    assert ds["coverage"]["analyticsMunicipalityCount"] == 2  # synthetic ZMB fixture


def test_warm_refuses_to_publish_a_zero_coverage_regression(isolated_cache, zmb_only, monkeypatch):
    """A live fetch that succeeds (no exception) but joins to zero
    municipalities -- e.g. Nepal's live boundary table currently being
    district-level only -- must not overwrite working bundled/cached data.
    Fake a live feature collection whose compositeKeys can't possibly match
    ZMB's analytics rows and confirm warm() holds back the publish."""
    monkeypatch.setattr(
        queries, "_assemble_feature_collection",
        lambda code: {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"compositeKey": "Nowhere::Nowhere::Nowhere"}, "geometry": None}
        ]},
    )
    man = datastore.warm(force=True)

    assert man["countries"] == []
    assert "ZMB" in man["regressed_countries"]
    cache_dir = datastore.CACHE_DIR
    assert not os.path.exists(os.path.join(cache_dir, datastore._analytics_name("ZMB")))
    assert not os.path.exists(os.path.join(cache_dir, datastore._boundary_name("ZMB")))

    # requests still get served -- from the bundled fallback, which the live
    # fetch was correctly refused permission to clobber.
    ds = datastore.analytics_dataset("ZMB")
    fc = datastore.boundary_geojson("ZMB")
    assert ds["municipalities"] and fc["features"]


def test_warm_isolates_one_countrys_failure_from_the_others(isolated_cache, monkeypatch):
    """The fake executor only knows Zambia's tables (see conftest.py), so with
    every country in play, NPL/SRB's queries raise while ZMB's succeed. warm()
    must still persist ZMB's artifacts and report success instead of the one
    failure wiping out every country's chance to be written this run."""
    monkeypatch.setattr(queries, "_list_volume_tree", lambda *a, **k: [])
    man = datastore.warm(force=True)

    assert man["countries"] == ["ZMB"]
    assert set(man["failed_countries"]) == {"NPL", "SRB"}
    cache_dir = datastore.CACHE_DIR
    assert os.path.exists(os.path.join(cache_dir, datastore._analytics_name("ZMB")))
    assert not os.path.exists(os.path.join(cache_dir, datastore._analytics_name("NPL")))

    ds = datastore.analytics_dataset("ZMB")
    assert ds["coverage"]["analyticsMunicipalityCount"] == 2  # synthetic ZMB fixture


def test_accessor_never_calls_databricks(isolated_cache, zmb_only, monkeypatch):
    def _boom(*_a, **_k):
        raise AssertionError("datastore accessor hit the live query path")

    # After warm, artifacts exist -> accessors must be pure disk reads.
    datastore.warm(force=True)
    monkeypatch.setattr(queries, "execute_query", _boom)
    with datastore._MEMO_LOCK:
        datastore._MEMO.clear()
    ds = datastore.analytics_dataset("ZMB")
    fc = datastore.boundary_geojson("ZMB")
    assert ds["municipalities"] and fc["features"]
