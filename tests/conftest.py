"""
Shared pytest fixtures.

The Databricks connector is never touched: ``queries.execute_query`` is
monkeypatched to return small synthetic DataFrames whose column names match
the source CSVs described in wb-ldt-app/scripts/lib/nepal-data.mjs, so the
assembler's expected output is known exactly.
"""

from __future__ import annotations

import os

# queries.py raises EnvironmentError at import unless these are set.
os.environ.setdefault("DATABRICKS_SERVER_HOSTNAME", "test.databricks.net")
os.environ.setdefault("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/test")
os.environ.setdefault("DATABRICKS_CLIENT_ID", "test-client")
os.environ.setdefault("DATABRICKS_CLIENT_SECRET", "test-secret")
os.environ.setdefault("QUERY_CACHE_TTL_SECONDS", "300")

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

import constants  # noqa: E402
import queries  # noqa: E402


# --- synthetic Zambia rows -------------------------------------------------
# admin_columns for ZMB: municipality="District", district="Province",
# province="Province"  -> compositeKey "Province::Province::District".

_ZMB_ADMIN_ROWS = [
    {
        "Province": "Central", "District": "Chitambo", "Year": 2024,
        "Population": 100000, "Total Land Area (km2)": 5000,
        "Total Road Length (km)": 120, "Total Railway Length (km)": 0,
        "Road Flood Risk (km)": 3, "Road Heatwave Risk (km)": 10,
        "Railway Flood Risk (km)": 0, "Railway Heatwave Risk (km)": 0,
        "Accessibility to Hospitals (%)": 40, "Accessibility to Schools (%)": 55,
        "Average PM25 Concentration (ug/m3)": 12.5,
        "Nighttime Luminosity": 900.0,
        "Change in Build Area (%)": 20.0,
    },
    {
        "Province": "Central", "District": "Chitambo", "Year": 2025,
        "Population": 105000, "Total Land Area (km2)": 5000,
        "Total Road Length (km)": 125, "Total Railway Length (km)": 0,
        "Road Flood Risk (km)": 3, "Road Heatwave Risk (km)": 11,
        "Railway Flood Risk (km)": 0, "Railway Heatwave Risk (km)": 0,
        "Accessibility to Hospitals (%)": 42, "Accessibility to Schools (%)": 57,
        "Average PM25 Concentration (ug/m3)": 11.9,
        "Nighttime Luminosity": 950.0,
        "Change in Build Area (%)": 22.0,
    },
    {
        "Province": "Lusaka", "District": "Lusaka", "Year": 2025,
        "Population": 3000000, "Total Land Area (km2)": 420,
        "Total Road Length (km)": 900, "Total Railway Length (km)": 30,
        "Road Flood Risk (km)": 12, "Road Heatwave Risk (km)": 40,
        "Railway Flood Risk (km)": 1, "Railway Heatwave Risk (km)": 2,
        "Accessibility to Hospitals (%)": 85, "Accessibility to Schools (%)": 90,
        "Average PM25 Concentration (ug/m3)": 18.0,
        "Nighttime Luminosity": 40000.0,
        "Change in Build Area (%)": 60.0,
    },
]

_ZMB_SCORE_ROWS = [
    {
        "Province": "Central", "District": "Chitambo", "Year": 2024,
        "Broadband Internet Score": 30, "Mobile Internet Score": 40,
        "Key Structure Internet Access Score": 35,
        "Accessibility to Hospitals Score": 41, "Accessibility to Schools Score": 44,
        "Emissions Score": 50, "Air Quality Score": 70, "Deforestation Score": 55,
        "Emissions Normalized Score": 48, "Railway Heatwave Score": 53,
        "Road Heatwave Score": 58, "Road Flood Score": 59, "Railway Flood Score": 51,
        "Luminosity per Capita Score": 12, "Luminosity per Area Score": 18,
        "Built Area Development Score": 45, "Tourism Score": 40, "Agricultural Land Score": 78,
        "Infrastructure Score": 38, "Livability Score": 54, "Prosperity Score": 39,
    },
    {
        "Province": "Central", "District": "Chitambo", "Year": 2025,
        "Broadband Internet Score": 33, "Mobile Internet Score": 44,
        "Key Structure Internet Access Score": 37,
        "Accessibility to Hospitals Score": 43, "Accessibility to Schools Score": 46,
        "Emissions Score": 52, "Air Quality Score": 72, "Deforestation Score": 57,
        "Emissions Normalized Score": 49, "Railway Heatwave Score": 54,
        "Road Heatwave Score": 59, "Road Flood Score": 60, "Railway Flood Score": 52,
        "Luminosity per Capita Score": 14, "Luminosity per Area Score": 20,
        "Built Area Development Score": 48, "Tourism Score": 42, "Agricultural Land Score": 80,
        "Infrastructure Score": 41, "Livability Score": 57, "Prosperity Score": 41,
    },
    {
        "Province": "Lusaka", "District": "Lusaka", "Year": 2025,
        "Broadband Internet Score": 80, "Mobile Internet Score": 85,
        "Key Structure Internet Access Score": 78,
        "Accessibility to Hospitals Score": 88, "Accessibility to Schools Score": 90,
        "Emissions Score": 40, "Air Quality Score": 45, "Deforestation Score": 60,
        "Emissions Normalized Score": 42, "Railway Heatwave Score": 55,
        "Road Heatwave Score": 50, "Road Flood Score": 48, "Railway Flood Score": 52,
        "Luminosity per Capita Score": 70, "Luminosity per Area Score": 92,
        "Built Area Development Score": 95, "Tourism Score": 80, "Agricultural Land Score": 20,
        "Infrastructure Score": 84, "Livability Score": 47, "Prosperity Score": 71,
    },
]

# One boundary row per admin-2 unit (WKT). Lusaka intentionally has TWO rows
# to exercise the multi-row merge.
_ZMB_BOUNDARY_ROWS = [
    {"NAM_1": "Central", "NAM_2": "Chitambo",
     "geometry_wkt": "POLYGON ((28 -13, 29 -13, 29 -14, 28 -14, 28 -13))"},
    {"NAM_1": "Lusaka", "NAM_2": "Lusaka",
     "geometry_wkt": "POLYGON ((28 -15, 28.5 -15, 28.5 -15.5, 28 -15.5, 28 -15))"},
    {"NAM_1": "Lusaka", "NAM_2": "Lusaka",
     "geometry_wkt": "POLYGON ((28.5 -15, 29 -15, 29 -15.5, 28.5 -15.5, 28.5 -15))"},
    # a boundary with no matching analytics row
    {"NAM_1": "Copperbelt", "NAM_2": "Ndola",
     "geometry_wkt": "POLYGON ((28 -12, 29 -12, 29 -13, 28 -13, 28 -12))"},
]


def _fake_execute_query(query: str) -> pd.DataFrame:
    q = query.lower()
    if "gpbp_ldt_zmb_admin_2" in q and "scores" not in q:
        return pd.DataFrame(_ZMB_ADMIN_ROWS)
    if "gpbp_ldt_zmb_scores_admin_2" in q:
        return pd.DataFrame(_ZMB_SCORE_ROWS)
    if "ldt_boundaries_admin2_zambia" in q:
        return pd.DataFrame(_ZMB_BOUNDARY_ROWS)
    raise AssertionError(f"unexpected query in test: {query}")


@pytest.fixture(autouse=True)
def _mock_databricks(monkeypatch):
    monkeypatch.setattr(queries, "execute_query", _fake_execute_query)
    queries.clear_caches()
    yield
    queries.clear_caches()


@pytest.fixture
def zmb_dataset():
    return queries.get_analytics_dataset("ZMB")
