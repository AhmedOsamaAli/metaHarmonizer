"""App-side KB retrieval tests.

The FAISS vector retrieval lives inside the upstream engine (needs the full KB
bundle — covered by the gated real-engine ontology job). What the *app* owns and
must keep working is:

  1. the ``/ontology/search`` index, built from the real curated NCIT/UBERON KB
     data, and its fuzzy retrieval, and
  2. ``_corpus_label_to_id`` — recovering an ontology code from the KB corpus by
     label (the engine returns only the label).

These run without torch/FAISS/models, so they belong in the fast suite.
"""

from __future__ import annotations

import pytest

from app.routers.ontology import _SEARCH_INDEX, search_ontology


def test_search_index_built_from_real_kb() -> None:
    # Built at import from ONTOLOGY_MAP + field_value_dict.json (real KB data).
    assert len(_SEARCH_INDEX) > 50
    for entry in _SEARCH_INDEX[:25]:
        assert entry["term"]
        assert entry["ontology"]
        assert entry["ontology_id"]
        assert entry["search_key"]


@pytest.mark.asyncio
async def test_ontology_search_retrieves_an_indexed_term() -> None:
    sample = _SEARCH_INDEX[0]
    term = sample["term"]

    results = await search_ontology(query=term, ontology="", limit=25)

    assert results, f"no results for indexed term {term!r}"
    matched = [r for r in results if r.term.lower() == term.lower()]
    assert matched, f"search for {term!r} did not return itself"
    top = matched[0]
    assert 0.0 <= top.score <= 1.0
    assert ":" in top.ontology_id  # e.g. NCIT:C2955 / UBERON:0001988


@pytest.mark.asyncio
async def test_ontology_search_filter_by_prefix() -> None:
    prefixes = {e["ontology"] for e in _SEARCH_INDEX}
    assert prefixes
    prefix = "NCIT" if "NCIT" in prefixes else next(iter(prefixes))

    results = await search_ontology(query="a", ontology=prefix, limit=15)

    assert all(r.ontology == prefix for r in results)


def test_corpus_label_to_id_recovers_codes(tmp_path, monkeypatch) -> None:
    from app.engine_adapter import _ontology

    corpus_dir = tmp_path / "corpus" / "retrieved_ontologies"
    corpus_dir.mkdir(parents=True)
    (corpus_dir / "ncit_disease_corpus.csv").write_text(
        "label,obo_id\ncolorectal carcinoma,NCIT:C2955\nadenoma,NCIT:C2855\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("METAHARMONIZER_DATA_DIR", str(tmp_path))
    _ontology._corpus_label_to_id.cache_clear()
    try:
        mapping = _ontology._corpus_label_to_id("disease", "ncit")
        assert mapping["colorectal carcinoma"] == "NCIT:C2955"
        assert mapping["adenoma"] == "NCIT:C2855"
    finally:
        _ontology._corpus_label_to_id.cache_clear()
