"""Regression guards for two real-engine bugs found in the e2e pass:

1. Schema-mapping confidence could exceed 1.0 (stage-3 similarity).
2. cBioPortal export rendered missing values as the literal string "nan".

Both need pandas (the engine adapter + exporter import it), so the module
skips gracefully in the lightweight test venv.
"""

from __future__ import annotations

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


