"""Score-driver waterfall maths."""

from __future__ import annotations

import queries


def test_waterfall_structure_and_totals(zmb_dataset):
    municipalities_2025 = queries.get_municipalities_for_year("ZMB", 2025)
    selected = next(m for m in municipalities_2025 if m["municipality"] == "Lusaka")
    groups = queries.build_score_waterfalls("ZMB", selected, municipalities_2025)

    assert [g["scoreId"] for g in groups] == [
        "infrastructure_score", "livability_score", "prosperity_score",
    ]
    infra = groups[0]
    assert infra["municipalityScore"] == 84
    # national infra avg over 2025 = mean(41, 84) = 62.5
    assert infra["nationalScore"] == 62.5
    assert infra["totalDifference"] == round(84 - 62.5, 2)
    assert len(infra["rows"]) == 5
    for row in infra["rows"]:
        assert {"componentId", "label", "municipalityValue", "nationalValue", "contribution"} <= row.keys()


def test_waterfall_handles_missing_component(zmb_dataset):
    municipalities_2025 = queries.get_municipalities_for_year("ZMB", 2025)
    selected = dict(municipalities_2025[0])
    selected["scoreComponents"] = {}  # nothing populated
    groups = queries.build_score_waterfalls("ZMB", selected, municipalities_2025)
    # still returns 3 groups, contributions are None, no ZeroDivisionError
    assert len(groups) == 3
    assert all(r["contribution"] is None for g in groups for r in g["rows"])
