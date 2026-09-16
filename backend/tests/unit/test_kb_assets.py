from __future__ import annotations

import sqlite3
from pathlib import Path

from app.engine_adapter import kb_assets


def _complete_tree(root: Path) -> dict[str, Path]:
    paths = {
        "vector_db": root / "knowledge/vector_db.sqlite",
        "faiss_dir": root / "knowledge/faiss_indexes",
        "corpus_dir": root / "data/corpus/retrieved_ontologies",
        "model_cache_dir": root / "model_cache",
        "hf_hub_root": root / "hf_hub",
    }
    paths["vector_db"].parent.mkdir(parents=True)
    with sqlite3.connect(paths["vector_db"]) as db:
        for category, source in kb_assets.REQUIRED_ONTOLOGY_TUPLES:
            for table in (
                f"{source}_corpus_{category}",
                f"{source}_rag_{category}",
                f"{source}_synonym_{category}",
            ):
                db.execute(f'CREATE TABLE "{table}" (id INTEGER)')
                db.execute(f'INSERT INTO "{table}" VALUES (1)')
    paths["faiss_dir"].mkdir()
    paths["corpus_dir"].mkdir(parents=True)
    for category, source in kb_assets.REQUIRED_ONTOLOGY_TUPLES:
        (paths["corpus_dir"] / f"{source}_{category}_corpus.csv").write_text(
            "label,obo_id\nterm,ID:1\n",
            encoding="utf-8",
        )
        index = paths["faiss_dir"] / f"st_sap_bert_{source}_{category}.index"
        index.write_bytes(b"index")
        index.with_suffix(".index.ids.npy").write_bytes(b"ids")
        (
            paths["faiss_dir"] / f"synonym_sap_bert_{source}_{category}.index"
        ).write_bytes(b"synonyms")
    ontology_model = paths["model_cache_dir"] / "sap-bert/model.safetensors"
    ontology_model.parent.mkdir(parents=True)
    ontology_model.write_bytes(b"model")
    schema_model = (
        paths["hf_hub_root"]
        / kb_assets.SCHEMA_MODEL_DIR
        / "snapshots/revision/model.safetensors"
    )
    schema_model.parent.mkdir(parents=True)
    schema_model.write_bytes(b"model")
    return paths


def test_installed_kb_contract_accepts_complete_tree(tmp_path: Path) -> None:
    assert kb_assets.installed_kb_issues(**_complete_tree(tmp_path)) == []


def test_installed_kb_contract_reports_missing_index_sidecar(tmp_path: Path) -> None:
    paths = _complete_tree(tmp_path)
    sidecar = next(paths["faiss_dir"].glob("*disease.index.ids.npy"))
    sidecar.unlink()

    issues = kb_assets.installed_kb_issues(**paths)

    assert any("id sidecar" in issue and "disease" in issue for issue in issues)


def test_installed_kb_contract_reports_missing_synonym_index(tmp_path: Path) -> None:
    paths = _complete_tree(tmp_path)
    synonym = paths["faiss_dir"] / "synonym_sap_bert_uberon_bodysite.index"
    synonym.unlink()

    issues = kb_assets.installed_kb_issues(**paths)

    assert issues == [f"missing exact sap-bert synonym index: {synonym}"]


def test_bundle_contract_requires_every_runtime_asset() -> None:
    members = {
        "kb.mhkb.tar.gz",
        "nci_schema_cache.json",
        "model_cache/sap-bert/model.safetensors",
        f"hf_hub/{kb_assets.SCHEMA_MODEL_DIR}/snapshots/revision/model.safetensors",
        *(
            f"corpus/retrieved_ontologies/{name}"
            for name in kb_assets.REQUIRED_CORPUS_NAMES
        ),
    }
    assert kb_assets.bundle_member_issues(members) == []

    members.remove("corpus/retrieved_ontologies/uberon_bodysite_corpus.csv")
    assert kb_assets.bundle_member_issues(members) == [
        "missing bundle member: "
        "corpus/retrieved_ontologies/uberon_bodysite_corpus.csv"
    ]


def test_runtime_requirement_tracks_real_ontology_configuration(monkeypatch) -> None:
    monkeypatch.setenv("ENGINE_IMPL", "metaharmonizer")
    monkeypatch.setenv("ONTOLOGY_ENGINE", "1")
    assert kb_assets.runtime_engine_required()
    assert kb_assets.runtime_ontology_required()

    monkeypatch.setenv("ENGINE_IMPL", "mock")
    assert not kb_assets.runtime_engine_required()
    assert not kb_assets.runtime_ontology_required()


def test_real_schema_engine_requires_model_even_when_ontology_is_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ENGINE_IMPL", "metaharmonizer")
    monkeypatch.setenv("ONTOLOGY_ENGINE", "0")
    paths = _complete_tree(tmp_path)
    schema_model = next(paths["hf_hub_root"].rglob("model.safetensors"))
    schema_model.unlink()

    issues = kb_assets.installed_kb_issues(
        **paths,
        require_engine_db=False,
        require_ontology_model=False,
        require_schema_model=True,
        tuples=(),
    )

    assert issues == [
        "missing schema model snapshot: "
        f"{paths['hf_hub_root'] / kb_assets.SCHEMA_MODEL_DIR / 'snapshots'}"
    ]
