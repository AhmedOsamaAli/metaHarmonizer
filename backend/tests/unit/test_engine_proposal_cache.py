from __future__ import annotations

from contextlib import contextmanager

import pandas as pd

from app.services import engine_proposal_cache as cache
from app.workers import tasks


def test_cache_scopes_are_version_isolated():
    a = cache.scopes(
        schema_version_id=1,
        ontology_snapshot_id=2,
        target_schema="cbioportal",
        engine_version="0.4.1",
    )
    b = cache.scopes(
        schema_version_id=1,
        ontology_snapshot_id=3,
        target_schema="cbioportal",
        engine_version="0.4.1",
    )
    c = cache.scopes(
        schema_version_id=1,
        ontology_snapshot_id=2,
        target_schema="cbioportal",
        engine_version="0.5.0",
    )
    assert a[0] == b[0]
    assert a[1] != b[1]
    assert a != c


def test_hydration_requires_complete_schema_hit():
    columns = ["Patient ID", "Biopsy Site"]
    cached = {
        "patient id": {"matched_field": "patient_id", "status": "accepted"},
        "biopsy site": {"matched_field": "body_site", "status": "pending"},
    }
    rows = cache.hydrate_schema(columns, cached)
    assert [row["raw_column"] for row in rows] == columns
    assert cache.hydrate_schema(columns, {"patient id": cached["patient id"]}) is None


def test_complete_cache_hit_skips_engine(monkeypatch, tmp_path):
    csv_path = tmp_path / "study.csv"
    pd.DataFrame({"site": ["lung", "liver"]}).to_csv(csv_path, index=False)

    class Storage:
        @contextmanager
        def local(self, key):
            yield csv_path

    monkeypatch.setattr(tasks, "get_storage", lambda: Storage())
    monkeypatch.setattr(
        tasks,
        "get_engine",
        lambda: (_ for _ in ()).throw(AssertionError("engine must not run on a complete hit")),
    )

    schema = [
        {
            "raw_column": "site",
            "matched_field": "body_site",
            "confidence_score": 0.95,
            "stage": "stage1",
            "method": "cached",
            "alternatives": [],
            "status": "accepted",
        }
    ]
    ontology = [
        {
            "field_name": "body_site",
            "raw_value": "lung",
            "ontology_term": "Lung",
            "ontology_id": "UBERON:0002048",
            "confidence_score": 1.0,
            "status": "accepted",
        },
        {
            "field_name": "body_site",
            "raw_value": "liver",
            "ontology_term": "Liver",
            "ontology_id": "UBERON:0002107",
            "confidence_score": 1.0,
            "status": "accepted",
        },
    ]

    result = tasks._run_pipeline(
        "study",
        "study.csv",
        ".csv",
        "curated.csv",
        mode="both",
        cached_schema=schema,
        cached_ontology=ontology,
    )
    assert result["schema_cache_hit"] is True
    assert result["ontology_cache_hit"] is True
    assert result["schema_results"] == schema
    assert result["onto_results"] == ontology
