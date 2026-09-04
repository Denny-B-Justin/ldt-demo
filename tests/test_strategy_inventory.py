"""Strategy inventory built from a fake documents Volume tree."""

from __future__ import annotations

import pytest

import queries


_FAKE_FILES = [
    {"path": "/Volumes/.../Serbia/Belgrade-Barajevo/Local Development Strategy 2023-2030.pdf",
     "name": "Local Development Strategy 2023-2030.pdf", "parent": "Belgrade-Barajevo", "size": 1000},
    {"path": "/Volumes/.../Serbia/Belgrade-Barajevo/Budget 2024.xlsx",
     "name": "Budget 2024.xlsx", "parent": "Belgrade-Barajevo", "size": 500},
    {"path": "/Volumes/.../Serbia/Novi Sad/Strategija razvoja 2021 sr.docx",
     "name": "Strategija razvoja 2021 sr.docx", "parent": "Novi Sad", "size": 800},
    {"path": "/Volumes/.../Serbia/Nis/notes.png",
     "name": "notes.png", "parent": "Nis", "size": 10},
]


@pytest.fixture(autouse=True)
def _fake_volume(monkeypatch):
    monkeypatch.setattr(queries, "_list_volume_tree", lambda *a, **k: list(_FAKE_FILES))


def test_records_derived_per_file():
    ds = queries.get_strategy_inventory_dataset("SRB")
    assert ds is not None
    assert ds["is_sample_data"] is False
    assert len(ds["records"]) == 4
    by_title = {r["document_title"]: r for r in ds["records"]}

    strat = by_title["Local Development Strategy 2023-2030"]
    assert strat["document_type"] == "strategy"
    assert strat["publication_year"] == 2030
    assert strat["parsing_status"] == "parsed"
    assert strat["lsg_name"] == "Belgrade-Barajevo"

    budget = by_title["Budget 2024"]
    assert budget["document_type"] == "budget"
    assert budget["publication_year"] == 2024

    png = by_title["notes"]
    assert png["parsing_status"] == "needs_review"


def test_language_detection():
    ds = queries.get_strategy_inventory_dataset("SRB")
    srp = next(r for r in ds["records"] if r["document_title"].startswith("Strategija"))
    assert srp["language"] == "sr"


def test_summary_totals():
    ds = queries.get_strategy_inventory_dataset("SRB")
    summary = queries.get_strategy_inventory_summary(
        ds["records"], ds["expected_lsg_count"], ds.get("summary_override")
    )
    assert summary["total_documents_found"] == 4
    assert summary["strategies_found"] == 2
    assert summary["budgets_found"] == 1
    assert summary["expected_lsgs"] == 161


def test_nepal_has_no_inventory():
    assert queries.get_strategy_inventory_dataset("NPL") is None
