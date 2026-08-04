"""Regression guards for two real-engine bugs found in the e2e pass:

1. Schema-mapping confidence could exceed 1.0 (stage-3 similarity).
2. cBioPortal export rendered missing values as the literal string "nan".

Both need pandas (the engine adapter + exporter import it), so the module
skips gracefully in the lightweight test venv.
"""

from __future__ import annotations

import csv
import io

import pytest

pytest.importorskip("pandas")
import pandas as pd  # noqa: E402


def test_to_score_clamps_to_unit_interval():
    from app.engine_adapter.metaharmonizer_impl import MetaHarmonizerAdapter as A

    assert A._to_score(1.046) == 1.0
    assert A._to_score(-0.2) == 0.0
    assert A._to_score(0.5) == 0.5
    assert A._to_score(None) == 0.0
    assert A._to_score(float("nan")) == 0.0


def test_cbioportal_export_blanks_missing_values():
    from app.services import exporter

    assert exporter._sanitize_id(pd.NA) == ""
    assert exporter._normalize_survival(float("nan")) == ""
    # A real value still passes through.
    assert exporter._sanitize_id("MG100208") == "MG100208"


def test_guard_formula_injection_escapes_formulas_not_numbers():
    from app.services import exporter

    # Formula triggers get a leading apostrophe so a spreadsheet renders them
    # as literal text (CSV-injection defense on the human-facing CSV export).
    assert exporter._guard_formula_injection("=SUM(A1:A9)") == "'=SUM(A1:A9)"
    assert exporter._guard_formula_injection("@foo") == "'@foo"
    assert exporter._guard_formula_injection("+cmd|'/c calc'!A1") == "'+cmd|'/c calc'!A1"
    assert exporter._guard_formula_injection("-2+3+cmd") == "'-2+3+cmd"
    # Plain numbers and ordinary text are left untouched.
    assert exporter._guard_formula_injection("-5") == "-5"
    assert exporter._guard_formula_injection("+3.1") == "+3.1"
    assert exporter._guard_formula_injection("healthy") == "healthy"
    assert exporter._guard_formula_injection("") == ""


def test_value_rewrite_map_applies_accepted_terms():
    """U5: a column's accepted raw_value -> term mapping rewrites cells; others pass through."""
    lookup = {"adult": "Adult", "stool": "feces"}
    col = pd.Series(["adult", "stool", "weird", None])
    rewritten = col.map(lambda v, _m=lookup: _m.get(str(v), v) if pd.notna(v) else v)
    assert list(rewritten) == ["Adult", "feces", "weird", None]


async def test_harmonized_export_dedupes_target_columns(monkeypatch):
    """Many source columns -> one target field must yield a single, non-duplicated
    output column: accepted beats pending, then higher confidence wins."""
    from app.repositories import mappings as mappings_repo
    from app.repositories import ontology as ontology_repo
    from app.services import exporter

    raw_df = pd.DataFrame({
        "dx": ["a", "b"],
        "diagnosis": ["c", "d"],
        "primary_disease": ["e", "f"],
        "age": [1, 2],
    })
    mappings = [
        {"raw_column": "dx", "matched_field": "disease", "curator_field": None,
         "confidence_score": 0.72, "status": "pending"},
        {"raw_column": "diagnosis", "matched_field": "disease", "curator_field": "disease",
         "confidence_score": 0.95, "status": "accepted"},
        {"raw_column": "primary_disease", "matched_field": "disease", "curator_field": None,
         "confidence_score": 0.80, "status": "pending"},
        {"raw_column": "age", "matched_field": "age_at_procurement", "curator_field": None,
         "confidence_score": 0.60, "status": "pending"},
    ]

    async def _get_mappings(_db, _sid):
        return mappings

    async def _no_onto(_db, _sid):
        return []

    monkeypatch.setattr(mappings_repo, "get_mappings", _get_mappings)
    monkeypatch.setattr(ontology_repo, "get_ontology_mappings", _no_onto)

    out = await exporter.export_harmonized_csv(db=None, study_id="s", raw_df=raw_df)
    lines = out.splitlines()
    header = lines[0].split(",")
    # 'disease' appears exactly once (no duplicate columns) and 'age' mapped too.
    assert header.count("disease") == 1
    assert "age_at_procurement" in header
    # The accepted, highest-confidence source ('diagnosis' -> c,d) won.
    assert lines[1].split(",")[header.index("disease")] == "c"


async def test_harmonized_export_uses_curator_override_and_preserves_rejected_raw(monkeypatch):
    from app.repositories import mappings as mappings_repo
    from app.repositories import ontology as ontology_repo
    from app.services import exporter

    raw_df = pd.DataFrame({
        "engine_column": ["raw", "other"],
        "rejected_column": ["keep me", "keep me too"],
    })
    mappings = [
        {
            "raw_column": "engine_column",
            "matched_field": "engine_target",
            "curator_field": "approved_target",
            "confidence_score": 0.4,
            "status": "accepted",
        },
        {
            "raw_column": "rejected_column",
            "matched_field": "rejected_engine_target",
            "curator_field": None,
            "confidence_score": 0.9,
            "status": "rejected",
        },
    ]
    ontology = [
        {
            "field_name": "approved_target",
            "raw_value": "raw",
            "ontology_term": "Engine Term",
            "curator_term": "Curator Term",
            "status": "accepted",
        },
        {
            "field_name": "approved_target",
            "raw_value": "other",
            "ontology_term": "Rejected Term",
            "curator_term": None,
            "status": "rejected",
        },
    ]

    async def _mappings(_db, _sid):
        return mappings

    async def _ontology(_db, _sid):
        return ontology

    monkeypatch.setattr(mappings_repo, "get_mappings", _mappings)
    monkeypatch.setattr(ontology_repo, "get_ontology_mappings", _ontology)

    out = await exporter.export_harmonized_csv(None, "study", raw_df)
    rows = list(csv.DictReader(io.StringIO(out)))
    assert list(rows[0]) == ["approved_target", "rejected_column"]
    assert rows[0]["approved_target"] == "Curator Term"
    assert rows[1]["approved_target"] == "other"
    assert rows[0]["rejected_column"] == "keep me"
    assert "engine_target" not in rows[0]
    assert "rejected_engine_target" not in rows[0]


def test_cbioportal_specs_use_curator_target_and_exclude_rejected():
    from app.services import exporter

    raw_df = pd.DataFrame({"source": ["x"], "rejected": ["y"]})
    mappings = [
        {
            "raw_column": "source", "matched_field": "engine_field",
            "curator_field": "approved_field", "status": "accepted",
        },
        {
            "raw_column": "rejected", "matched_field": "wrong_field",
            "curator_field": None, "status": "rejected",
        },
    ]
    specs = exporter._clinical_column_specs(mappings, raw_df)
    assert [spec["target"] for spec in specs] == ["APPROVED_FIELD"]


