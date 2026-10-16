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


# --- synthetic Vietnam rows -------------------------------------------------
# Real ldt_indicators_vietnam / ldt_scores_vietnam schema: snake_case columns,
# lowercase "year", and no District column at all (Vietnam's July 2025
# reform collapsed the district tier) -- admin_columns for VNM maps
# district=Province, so compositeKey is "Province::Province::Municipality".

_VNM_ADMIN_ROWS = [
    {
        "Province": "Tỉnh A", "Municipality": "Xã Một", "year": 2024,
        "land_area_km2": 50, "population": 10000, "nighttime_luminosity": 500,
        "change_in_build_area_pct": 5, "change_in_forest_area_pct": -2,
        "total_land_area_for_agricultural_use_km2": 20,
        "co2_equivalent_emissions_tonnes": 1000,
        "average_pm25_concentration_ug_per_m3": 15,
        "average_broadband_internet_download_speed_mbps": 30,
        "average_mobile_internet_download_speed_mbps": 25,
        "key_structures_without_access_to_broadband_internet_pct": 10,
        "total_road_length_km": 40, "total_railway_length_km": 0,
        "road_flood_risk_km": 2, "railway_flood_risk_km": 0,
        "road_heatwave_risk_km": 5, "railway_heatwave_risk_km": 0,
        "number_of_tourism_pois": 3,
        "accessibility_to_hospitals_pct": 60, "accessibility_to_schools_pct": 70,
        "luminosity_per_capita": 0.05,
        "railway_flood_risk_pct": 0, "road_flood_risk_pct": 5,
        "railway_heatwave_risk_pct": 0, "road_heatwave_risk_pct": 12,
    },
    {
        "Province": "Tỉnh A", "Municipality": "Xã Một", "year": 2025,
        "land_area_km2": 50, "population": 10500, "nighttime_luminosity": 540,
        "change_in_build_area_pct": 6, "change_in_forest_area_pct": -1,
        "total_land_area_for_agricultural_use_km2": 19,
        "co2_equivalent_emissions_tonnes": 1050,
        "average_pm25_concentration_ug_per_m3": 14,
        "average_broadband_internet_download_speed_mbps": 32,
        "average_mobile_internet_download_speed_mbps": 27,
        "key_structures_without_access_to_broadband_internet_pct": 8,
        "total_road_length_km": 41, "total_railway_length_km": 0,
        "road_flood_risk_km": 2, "railway_flood_risk_km": 0,
        "road_heatwave_risk_km": 5, "railway_heatwave_risk_km": 0,
        "number_of_tourism_pois": 4,
        "accessibility_to_hospitals_pct": 63, "accessibility_to_schools_pct": 72,
        "luminosity_per_capita": 0.051,
        "railway_flood_risk_pct": 0, "road_flood_risk_pct": 5,
        "railway_heatwave_risk_pct": 0, "road_heatwave_risk_pct": 12,
    },
    {
        "Province": "Thành phố B", "Municipality": "Phường Hai", "year": 2025,
        "land_area_km2": 12, "population": 250000, "nighttime_luminosity": 9000,
        "change_in_build_area_pct": 15, "change_in_forest_area_pct": 0,
        "total_land_area_for_agricultural_use_km2": 1,
        "co2_equivalent_emissions_tonnes": 8000,
        "average_pm25_concentration_ug_per_m3": 22,
        "average_broadband_internet_download_speed_mbps": 80,
        "average_mobile_internet_download_speed_mbps": 60,
        "key_structures_without_access_to_broadband_internet_pct": 1,
        "total_road_length_km": 300, "total_railway_length_km": 5,
        "road_flood_risk_km": 20, "railway_flood_risk_km": 1,
        "road_heatwave_risk_km": 50, "railway_heatwave_risk_km": 1,
        "number_of_tourism_pois": 40,
        "accessibility_to_hospitals_pct": 95, "accessibility_to_schools_pct": 97,
        "luminosity_per_capita": 0.036,
        "railway_flood_risk_pct": 20, "road_flood_risk_pct": 7,
        "railway_heatwave_risk_pct": 20, "road_heatwave_risk_pct": 17,
    },
]

_VNM_SCORE_ROWS = [
    {
        "Province": "Tỉnh A", "Municipality": "Xã Một", "year": 2024,
        "broadband_internet_score": 30, "mobile_internet_score": 40,
        "key_structure_internet_access_score": 35,
        "accessibility_to_hospitals_score": 41, "accessibility_to_schools_score": 44,
        "railway_heatwave_score": 53, "road_heatwave_score": 58,
        "road_flood_score": 59, "railway_flood_score": 51,
        "emissions_normalized_score": 48, "air_quality_score": 70,
        "deforestation_score": 55, "emissions_score": 50,
        "luminosity_per_capita_score": 12, "luminosity_per_area_score": 18,
        "built_area_development_score": 45, "tourism_score": 40,
        "agricultural_land_score": 78,
        "infrastructure_score": 38, "livability_score": 54, "prosperity_score": 39,
    },
    {
        "Province": "Tỉnh A", "Municipality": "Xã Một", "year": 2025,
        "broadband_internet_score": 33, "mobile_internet_score": 44,
        "key_structure_internet_access_score": 37,
        "accessibility_to_hospitals_score": 43, "accessibility_to_schools_score": 46,
        "railway_heatwave_score": 54, "road_heatwave_score": 59,
        "road_flood_score": 60, "railway_flood_score": 52,
        "emissions_normalized_score": 49, "air_quality_score": 72,
        "deforestation_score": 57, "emissions_score": 52,
        "luminosity_per_capita_score": 14, "luminosity_per_area_score": 20,
        "built_area_development_score": 48, "tourism_score": 42,
        "agricultural_land_score": 80,
        "infrastructure_score": 41, "livability_score": 57, "prosperity_score": 41,
    },
    {
        "Province": "Thành phố B", "Municipality": "Phường Hai", "year": 2025,
        "broadband_internet_score": 80, "mobile_internet_score": 85,
        "key_structure_internet_access_score": 78,
        "accessibility_to_hospitals_score": 88, "accessibility_to_schools_score": 90,
        "railway_heatwave_score": 55, "road_heatwave_score": 50,
        "road_flood_score": 48, "railway_flood_score": 52,
        "emissions_normalized_score": 42, "air_quality_score": 45,
        "deforestation_score": 60, "emissions_score": 40,
        "luminosity_per_capita_score": 70, "luminosity_per_area_score": 92,
        "built_area_development_score": 95, "tourism_score": 80,
        "agricultural_land_score": 20,
        "infrastructure_score": 84, "livability_score": 47, "prosperity_score": 71,
    },
]

# Boundary table has only NAM_1 (province) / NAM_2 (municipality) / geometry_wkt
# -- no Province/Municipality/District columns at all.
_VNM_BOUNDARY_ROWS = [
    {"NAM_1": "Tỉnh A", "NAM_2": "Xã Một",
     "geometry_wkt": "POLYGON ((105 21, 106 21, 106 22, 105 22, 105 21))"},
    {"NAM_1": "Thành phố B", "NAM_2": "Phường Hai",
     "geometry_wkt": "POLYGON ((107 10, 108 10, 108 11, 107 11, 107 10))"},
    # a boundary with no matching analytics row
    {"NAM_1": "Tỉnh C", "NAM_2": "Xã Ba",
     "geometry_wkt": "POLYGON ((103 16, 104 16, 104 17, 103 17, 103 16))"},
]


def _fake_execute_query(query: str) -> pd.DataFrame:
    q = query.lower()
    if "gpbp_ldt_zmb_admin_2" in q and "scores" not in q:
        return pd.DataFrame(_ZMB_ADMIN_ROWS)
    if "gpbp_ldt_zmb_scores_admin_2" in q:
        return pd.DataFrame(_ZMB_SCORE_ROWS)
    if "ldt_boundaries_admin2_zambia" in q:
        return pd.DataFrame(_ZMB_BOUNDARY_ROWS)
    if "ldt_indicators_vietnam" in q:
        return pd.DataFrame(_VNM_ADMIN_ROWS)
    if "ldt_scores_vietnam" in q:
        return pd.DataFrame(_VNM_SCORE_ROWS)
    if "ldt_boundaries_admin2_vietnam" in q:
        return pd.DataFrame(_VNM_BOUNDARY_ROWS)
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


@pytest.fixture
def vnm_dataset():
    return queries.get_analytics_dataset("VNM")
