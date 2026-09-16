"""Completeness contract for the offline ontology knowledge-base bundle."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

REQUIRED_ONTOLOGY_TUPLES = (
    ("disease", "ncit"),
    ("bodysite", "uberon"),
    ("treatment", "ncit"),
)
REQUIRED_CORPUS_NAMES = tuple(
    f"{source}_{category}_corpus.csv" for category, source in REQUIRED_ONTOLOGY_TUPLES
)
SCHEMA_MODEL_DIR = "models--sentence-transformers--all-MiniLM-L6-v2"


def runtime_engine_required() -> bool:
    return os.getenv("ENGINE_IMPL", "metaharmonizer").strip().lower() == "metaharmonizer"


def runtime_ontology_required() -> bool:
    ontology = os.getenv("ONTOLOGY_ENGINE", "0").strip().lower()
    return runtime_engine_required() and ontology in {"1", "true", "yes", "on"}


def _nonempty(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def _default_paths() -> tuple[Path, Path, Path, Path, Path]:
    from metaharmonizer import _paths

    data_dir = Path(
        os.getenv(
            "METAHARMONIZER_DATA_DIR",
            Path(__file__).resolve().parents[2] / "data",
        )
    )
    hf_home = Path(os.getenv("HF_HOME", Path.home() / ".cache/huggingface"))
    return (
        _paths.VECTOR_DB_PATH,
        _paths.FAISS_INDEX_DIR,
        data_dir / "corpus/retrieved_ontologies",
        _paths.MODEL_CACHE_DIR,
        hf_home / "hub",
    )


def installed_kb_issues(
    *,
    vector_db: Path | None = None,
    faiss_dir: Path | None = None,
    corpus_dir: Path | None = None,
    model_cache_dir: Path | None = None,
    hf_hub_root: Path | None = None,
    require_engine_db: bool = True,
    require_ontology_model: bool = True,
    require_schema_model: bool = True,
    tuples: tuple[tuple[str, str], ...] = REQUIRED_ONTOLOGY_TUPLES,
) -> list[str]:
    if any(
        path is None
        for path in (vector_db, faiss_dir, corpus_dir, model_cache_dir, hf_hub_root)
    ):
        defaults = _default_paths()
        vector_db = vector_db or defaults[0]
        faiss_dir = faiss_dir or defaults[1]
        corpus_dir = corpus_dir or defaults[2]
        model_cache_dir = model_cache_dir or defaults[3]
        hf_hub_root = hf_hub_root or defaults[4]

    issues: list[str] = []
    if require_engine_db and not _nonempty(vector_db):
        issues.append(f"missing or empty engine database: {vector_db}")
    elif require_engine_db:
        try:
            with sqlite3.connect(f"file:{vector_db.as_posix()}?mode=ro", uri=True) as db:
                tables = {
                    name
                    for (name,) in db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                for category, source in tuples:
                    for table in (
                        f"{source}_corpus_{category}",
                        f"{source}_rag_{category}",
                        f"{source}_synonym_{category}",
                    ):
                        if table not in tables:
                            issues.append(f"missing engine database table: {table}")
                            continue
                        count = int(
                            db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                        )
                        if count <= 0:
                            issues.append(f"empty engine database table: {table}")
        except sqlite3.Error as exc:
            issues.append(f"invalid engine database {vector_db}: {exc}")

    for category, source in tuples:
        corpus = corpus_dir / f"{source}_{category}_corpus.csv"
        if not _nonempty(corpus):
            issues.append(f"missing or empty ontology corpus: {corpus}")

        index = faiss_dir / f"st_sap_bert_{source}_{category}.index"
        if not _nonempty(index):
            issues.append(f"missing exact sap-bert FAISS index: {index}")
            continue
        ids = index.with_suffix(".index.ids.npy")
        if not _nonempty(ids):
            issues.append(f"missing or empty FAISS id sidecar: {ids}")
        synonym_index = faiss_dir / f"synonym_sap_bert_{source}_{category}.index"
        if not _nonempty(synonym_index):
            issues.append(f"missing exact sap-bert synonym index: {synonym_index}")

    if require_ontology_model:
        ontology_model = model_cache_dir / "sap-bert/model.safetensors"
        if not _nonempty(ontology_model):
            issues.append(f"missing ontology model: {ontology_model}")
    if require_schema_model:
        schema_models = list(
            (hf_hub_root / SCHEMA_MODEL_DIR / "snapshots").glob("*/model.safetensors")
        )
        if not any(_nonempty(model) for model in schema_models):
            issues.append(
                "missing schema model snapshot: "
                f"{hf_hub_root / SCHEMA_MODEL_DIR / 'snapshots'}"
            )
    return issues


def bundle_member_issues(
    members: set[str],
) -> list[str]:
    normalized = {name.removeprefix("./") for name in members}
    required = {"kb.mhkb.tar.gz", "nci_schema_cache.json"}
    required.update(
        f"corpus/retrieved_ontologies/{name}" for name in REQUIRED_CORPUS_NAMES
    )
    issues = [f"missing bundle member: {name}" for name in sorted(required - normalized)]
    ontology_model = "model_cache/sap-bert/model.safetensors"
    if ontology_model not in normalized:
        issues.append(f"missing bundle member: {ontology_model}")
    schema_prefix = f"hf_hub/{SCHEMA_MODEL_DIR}/snapshots/"
    if not any(
        name.startswith(schema_prefix) and name.endswith("/model.safetensors")
        for name in normalized
    ):
        issues.append(f"missing schema model under: {schema_prefix}")
    return issues
