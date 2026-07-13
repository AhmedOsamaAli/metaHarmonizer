"""Unit tests for the F-11 ontology engine bridge.

These verify the *plumbing* — category routing, result normalization, and
graceful fallback — using a fake OntoMapEngine, so no ontology corpus / API key
is needed. The real FAISS run is exercised separately once the KB is built.
Needs pandas (the bridge builds a query frame), so it skips in the light venv.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pandas")
import pandas as pd  # noqa: E402

from app.engine_adapter import _ontology  # noqa: E402


def test_engine_enabled_reads_env(monkeypatch):
    monkeypatch.delenv("ONTOLOGY_ENGINE", raising=False)
    assert _ontology.engine_enabled() is False
    monkeypatch.setenv("ONTOLOGY_ENGINE", "1")
    assert _ontology.engine_enabled() is True
    monkeypatch.setenv("ONTOLOGY_ENGINE", "off")
    assert _ontology.engine_enabled() is False


def test_field_ontology_only_engine_ready_tuples():
    # NCIt-disease + UBERON-bodysite (+ NCIt-treatment) are first-class; EFO /
    # HANCESTRO must NOT be wired here (engine-team scope).
    assert _ontology.FIELD_ONTOLOGY["disease"] == ("disease", "ncit")
    assert _ontology.FIELD_ONTOLOGY["body_site"] == ("bodysite", "uberon")
    assert "ancestry" not in _ontology.FIELD_ONTOLOGY
    assert "hla" not in _ontology.FIELD_ONTOLOGY


def test_normalize_engine_rows():
    frame = pd.DataFrame(
        [
            {"query": "lung cancer", "match1": "Lung Carcinoma", "match1_id": "NCIT:C4878", "match1_score": 0.97},
            {"query": "weird value", "match1": None, "match1_id": None, "match1_score": 0.10},
        ]
    )
    rows = _ontology._normalize_engine_rows("disease", frame)
    assert rows[0] == {
        "field_name": "disease",
        "raw_value": "lung cancer",
        "ontology_term": "Lung Carcinoma",
        "ontology_id": "NCIT:C4878",
        "confidence_score": 0.97,
        "status": "accepted",
    }
    # Low-confidence / unmatched stays pending.
    assert rows[1]["status"] == "pending"
    assert rows[1]["ontology_term"] is None


def test_normalize_engine_rows_enriches_code_from_corpus(monkeypatch):
    # OntoMapEngine.run() emits only the matched *label*, no code column. When
    # category/source are known the adapter recovers the code from the corpus
    # (label -> obo_id) that the match came from.
    monkeypatch.setattr(
        _ontology, "_corpus_label_to_id",
        lambda category, source: {"Glioblastoma": "NCIT:C3058"},
    )
    frame = pd.DataFrame([{"query": "GBM", "match1": "Glioblastoma", "match1_score": 1.0}])
    rows = _ontology._normalize_engine_rows("disease", frame, "disease", "ncit")
    assert rows[0]["ontology_term"] == "Glioblastoma"
    assert rows[0]["ontology_id"] == "NCIT:C3058"


def test_normalize_engine_rows_no_corpus_lookup_without_category(monkeypatch):
    # Backward compat: with no category/source the corpus is never consulted and
    # the frame's own id (here absent) is used as-is.
    called = {"n": 0}

    def _boom(category, source):
        called["n"] += 1
        return {"Glioblastoma": "NCIT:C3058"}

    monkeypatch.setattr(_ontology, "_corpus_label_to_id", _boom)
    frame = pd.DataFrame([{"query": "GBM", "match1": "Glioblastoma", "match1_score": 1.0}])
    rows = _ontology._normalize_engine_rows("disease", frame)
    assert rows[0]["ontology_id"] is None
    assert called["n"] == 0


def test_corpus_label_to_id_reads_real_corpus():
    # Guards against corpus column drift (label/obo_id). Skips where the NCIt
    # disease corpus isn't seeded (e.g. the light CI image).
    _ontology._corpus_label_to_id.cache_clear()
    mapping = _ontology._corpus_label_to_id("disease", "ncit")
    if not mapping:
        pytest.skip("disease corpus not present in this environment")
    assert mapping.get("Glioblastoma") == "NCIT:C3058"


class _FakeEngine:
    """Stand-in for OntoMapEngine.run() returning a deterministic frame.

    Uses the engine >=0.4.0 constructor arg names (corpus_category, query_ls).
    """

    def __init__(self, *, corpus_category, query_ls, **kw):
        self.category = corpus_category
        self.query = query_ls

    def run(self):
        return pd.DataFrame(
            [{"query": q, "match1": q.title(), "match1_id": f"NCIT:{i}", "match1_score": 0.95}
             for i, q in enumerate(self.query)]
        )


class _Pkg:
    OntoMapEngine = _FakeEngine


def test_map_values_via_engine_routes_supported_fields():
    raw_df = pd.DataFrame({"dx": ["lung cancer", "melanoma"], "misc": ["a", "b"]})
    schema = [
        {"raw_column": "dx", "matched_field": "disease"},
        {"raw_column": "misc", "matched_field": "free_text"},  # unsupported -> not handled
    ]
    rows, handled = _ontology.map_values_via_engine(_Pkg(), raw_df, schema)
    assert handled == {"disease"}
    values = {r["raw_value"] for r in rows}
    assert values == {"lung cancer", "melanoma"}
    assert all(r["field_name"] == "disease" for r in rows)


class _RaisingEngine:
    def __init__(self, **kw):
        raise RuntimeError("no corpus / no UMLS_API_KEY")


class _RaisingPkg:
    OntoMapEngine = _RaisingEngine


def test_map_values_via_engine_falls_back_on_error():
    raw_df = pd.DataFrame({"dx": ["lung cancer"]})
    schema = [{"raw_column": "dx", "matched_field": "disease"}]
    rows, handled = _ontology.map_values_via_engine(_RaisingPkg(), raw_df, schema)
    # Engine failed -> nothing handled, so the caller falls back to the dict.
    assert rows == []
    assert handled == set()
