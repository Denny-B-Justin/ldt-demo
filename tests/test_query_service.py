"""QueryService cache behaviour + FQTN quoting."""

from __future__ import annotations

import time

import pandas as pd
import pytest

import constants
import queries


@pytest.fixture
def svc():
    s = queries.QueryService()
    return s


def test_fqtn_backtick_quoted():
    assert queries._fqtn("gpbp_ldt_zmb_admin_2") == (
        f"`{constants.LDT_CATALOG}`.`{constants.LDT_SCHEMA}`.`gpbp_ldt_zmb_admin_2`"
    )


def test_cache_hit_returns_deep_copy(svc, monkeypatch):
    calls = {"n": 0}

    def fake_connect(**_kwargs):
        calls["n"] += 1
        raise RuntimeError("should not connect on cache hit")

    df = pd.DataFrame({"a": [1, 2]})
    svc._cache_set("SELECT 1", df)

    out1 = svc.execute_query("SELECT 1")
    out2 = svc.execute_query("SELECT 1")
    out1.loc[0, "a"] = 999
    assert out2.loc[0, "a"] == 1  # not mutated by caller
    assert calls["n"] == 0


def test_cache_ttl_expiry(svc):
    df = pd.DataFrame({"a": [1]})
    svc._cache_set("q", df)
    # force expiry
    with svc._lock:
        expires_at, cached = svc._cache["q"]
        svc._cache["q"] = (time.time() - 1, cached)
    assert svc._cache_get("q") is None


def test_cache_max_entries_eviction(svc, monkeypatch):
    monkeypatch.setattr(constants, "QUERY_CACHE_MAX_ENTRIES", 3)
    for i in range(5):
        svc._cache_set(f"q{i}", pd.DataFrame({"a": [i]}))
    assert len(svc._cache) <= 3
    # oldest evicted, newest kept
    assert "q4" in svc._cache
    assert "q0" not in svc._cache
