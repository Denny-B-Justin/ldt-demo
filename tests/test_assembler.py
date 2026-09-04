"""Assembler shape + join correctness (Python port of buildCountryAnalyticsData)."""

from __future__ import annotations

import queries


def test_dataset_top_level_shape(zmb_dataset):
    for key in (
        "generatedAt", "release", "coverage", "metricIds", "provinces", "years",
        "indicatorDefinitions", "scoreDefinitions", "metrics", "nationalAverages",
        "provinceSummary", "municipalities", "mapFeatureKeys",
    ):
        assert key in zmb_dataset, f"missing top-level key {key}"


def test_years_and_provinces_sorted(zmb_dataset):
    assert zmb_dataset["years"] == [2024, 2025]
    assert zmb_dataset["provinces"] == ["Central", "Lusaka"]
    assert zmb_dataset["release"]["year"] == 2025
    assert zmb_dataset["release"]["key"] == "zmb-2025-v1"


def test_coverage_counts_latest_year(zmb_dataset):
    # 2 municipality rows in 2025 (Chitambo, Lusaka)
    assert zmb_dataset["coverage"]["analyticsMunicipalityCount"] == 2


def test_composite_key_and_hierarchy(zmb_dataset):
    chitambo = next(
        m for m in zmb_dataset["municipalities"]
        if m["municipality"] == "Chitambo" and m["year"] == 2025
    )
    # ZMB admin_columns: municipality=District, district=Province, province=Province
    assert chitambo["province"] == "Central"
    assert chitambo["district"] == "Central"
    assert chitambo["compositeKey"] == "Central::Central::Chitambo"
    assert chitambo["id"] == "zmb-central-central-chitambo"


def test_temporal_score_join(zmb_dataset):
    chitambo_2024 = next(
        m for m in zmb_dataset["municipalities"]
        if m["municipality"] == "Chitambo" and m["year"] == 2024
    )
    chitambo_2025 = next(
        m for m in zmb_dataset["municipalities"]
        if m["municipality"] == "Chitambo" and m["year"] == 2025
    )
    assert chitambo_2024["scores"]["infrastructure_score"] == 38
    assert chitambo_2025["scores"]["infrastructure_score"] == 41
    # component score, not a pillar score
    assert chitambo_2025["scoreComponents"]["broadband_internet_score"] == 33
    # canonical remap: "Emissions Normalized Score" -> emissions_per_area_score
    assert chitambo_2025["scoreComponents"]["emissions_per_area_score"] == 49


def test_indicator_canonical_mapping(zmb_dataset):
    chitambo_2025 = next(
        m for m in zmb_dataset["municipalities"]
        if m["municipality"] == "Chitambo" and m["year"] == 2025
    )
    # "Accessibility to Hospitals (%)" -> "accessibility-to-health-services"
    assert chitambo_2025["indicators"]["accessibility-to-health-services"] == 42
    assert chitambo_2025["context"]["population"] == 105000
    assert chitambo_2025["context"]["totalLandAreaKm2"] == 5000


def test_national_averages_rounding(zmb_dataset):
    # national averages span every municipality-year row (matches nepal-data.mjs):
    # Chitambo 2024=38, Chitambo 2025=41, Lusaka 2025=84 -> 54.33
    avg = zmb_dataset["nationalAverages"]["scores"]["infrastructure_score"]
    assert avg == round((38 + 41 + 84) / 3, 2)


def test_province_summary(zmb_dataset):
    by_province = {p["province"]: p for p in zmb_dataset["provinceSummary"]}
    assert by_province["Central"]["municipalityCount"] == 1
    assert by_province["Lusaka"]["averageScores"]["prosperity_score"] == 71


def test_metrics_list(zmb_dataset):
    score_metrics = [m for m in zmb_dataset["metrics"] if m["kind"] == "score"]
    assert {m["id"] for m in score_metrics} == {
        "infrastructure_score", "livability_score", "prosperity_score",
    }
    assert any(m["kind"] == "indicator" for m in zmb_dataset["metrics"])


def test_page_data_map_coverage_label(zmb_dataset):
    page = queries.get_analytics_page_data("ZMB")
    # Chitambo + Lusaka boundaries match; Ndola does not.
    assert page["map"]["coverageLabel"].startswith("2 mapped of 2")
    assert page["coverage"]["mapMunicipalityCount"] == 2
