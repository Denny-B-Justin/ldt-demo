"""Vietnam-specific assembler regression tests.

Vietnam's Databricks schema (``ldt_indicators_vietnam`` / ``ldt_scores_vietnam``)
differs from Nepal/Serbia/Zambia's in two ways that silently dropped data
before being fixed:

1. It uses plain snake_case column names (e.g. ``accessibility_to_hospitals_pct``,
   ``land_area_km2``) rather than the NPL/SRB/ZMB-style titles the canonical
   mappings in constants.py are keyed on, so a handful of columns need the
   ``RAW_COLUMN_ALIASES`` entries in constants.py to resolve at all.
2. It has no District column (Vietnam's July 2025 administrative reform
   collapsed that tier) -- admin_columns for VNM maps district to Province
   instead.
"""

from __future__ import annotations


def test_district_falls_back_to_province(vnm_dataset):
    row = next(
        m for m in vnm_dataset["municipalities"]
        if m["municipality"] == "Xã Một" and m["year"] == 2025
    )
    assert row["province"] == "Tỉnh A"
    assert row["district"] == "Tỉnh A"
    assert row["compositeKey"] == "Tỉnh A::Tỉnh A::Xã Một"


def test_percent_suffixed_indicators_resolve_via_alias(vnm_dataset):
    row = next(
        m for m in vnm_dataset["municipalities"]
        if m["municipality"] == "Xã Một" and m["year"] == 2025
    )
    # accessibility_to_hospitals_pct -> "Accessibility to Hospitals (%)" ->
    # "Accessibility to Health Services (unit: %)"
    assert row["indicators"]["accessibility-to-health-services"] == 63
    assert row["indicators"]["accessibility-to-school-services"] == 72
    # key_structures_without_access_to_broadband_internet_pct
    assert row["indicators"]["key-structures-without-internet-access"] == 8
    # change_in_build_area_pct / change_in_forest_area_pct
    assert row["indicators"]["change-in-build-area"] == 6
    assert row["indicators"]["change-in-forest-area"] == -1
    # road_flood_risk_pct / road_heatwave_risk_pct / railway_*_risk_pct
    assert row["indicators"]["road-flood-risk"] == 5
    assert row["indicators"]["road-heatwave-risk"] == 12
    assert row["indicators"]["railway-flood-risk"] == 0
    assert row["indicators"]["railway-heatwave-risk"] == 0


def test_pm25_indicator_resolves_via_alias(vnm_dataset):
    row = next(
        m for m in vnm_dataset["municipalities"]
        if m["municipality"] == "Xã Một" and m["year"] == 2025
    )
    # average_pm25_concentration_ug_per_m3 -> "Average PM25 Concentration (ug/m3)"
    assert row["indicators"]["pm-2-5-concentration"] == 14


def test_total_land_area_context_resolves_via_alias(vnm_dataset):
    row = next(
        m for m in vnm_dataset["municipalities"]
        if m["municipality"] == "Xã Một" and m["year"] == 2025
    )
    # land_area_km2 -> "Total Land Area (km2)" -> context.totalLandAreaKm2
    assert row["context"]["totalLandAreaKm2"] == 50
    assert row["context"]["population"] == 10500


def test_columns_genuinely_absent_from_vietnam_stay_none(vnm_dataset):
    row = next(
        m for m in vnm_dataset["municipalities"]
        if m["municipality"] == "Xã Một" and m["year"] == 2025
    )
    # Vietnam's indicators table has no per-area emissions or luminosity-per-area
    # columns at all -- these should be absent/None, not raise or silently
    # pick up an unrelated column.
    assert row["indicators"].get("co2-equivalent-emissions-per-area") is None
    assert row["indicators"].get("luminosity-per-area") is None


def test_scores_resolve_without_any_alias(vnm_dataset):
    # Scores already match 1:1 once underscores/spaces are normalized away,
    # so this should work even without RAW_COLUMN_ALIASES.
    row = next(
        m for m in vnm_dataset["municipalities"]
        if m["municipality"] == "Xã Một" and m["year"] == 2025
    )
    assert row["scores"]["infrastructure_score"] == 41
    assert row["scoreComponents"]["broadband_internet_score"] == 33


def test_map_coverage_joins_on_nam1_nam2(vnm_dataset):
    import queries

    page = queries.get_analytics_page_data("VNM")
    # Xã Một (Tỉnh A) and Phường Hai (Thành phố B) both have matching
    # boundary rows; the third boundary row (Xã Ba) has no analytics match.
    assert page["coverage"]["mapMunicipalityCount"] == 2
    assert page["map"]["coverageLabel"].startswith("2 mapped of 2")
