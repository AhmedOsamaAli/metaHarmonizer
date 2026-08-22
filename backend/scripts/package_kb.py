"""Package a fully self-contained, offline KB bundle.

The engine's own ``knowledge_db export`` archive carries the FAISS indexes and
the ``vector_db.sqlite`` (corpus vectors + concept tables). But at *runtime* the
ontology engine resolves each corpus from a **CSV** under
``DATA_DIR/corpus/retrieved_ontologies/`` (``OntoMapEngine._resolve_corpus_df``),
and — if that CSV is absent — it re-downloads the entire ontology from NCI/OLS.
The schema stage similarly caches value→field lookups in
``backend/data/nci_schema_cache.json``.

Neither of those two assets travels in the engine archive, so a fresh
deployment that only imports the KB archive still hits the network on first use.
This script rolls everything a fresh instance needs into one bundle:

    kb.mhkb.tar.gz                      # engine KB (sqlite + faiss indexes)
    corpus/retrieved_ontologies/*.csv   # corpus CSVs the engine loads offline
    nci_schema_cache.json               # warmed schema value→field cache
    model_cache/**                      # engine ontology models (e.g. sap-bert)
    hf_hub/**                           # schema model HF snapshot (all-MiniLM-L6-v2)

The two model trees make a fresh box load its embedding models from disk with
``HF_HUB_OFFLINE=1`` instead of pulling them from HuggingFace on first use.
Pass ``--no-models`` to omit them (smaller bundle; models managed separately).

Install it with ``scripts/seed_kb.py``.

Usage::

    python -m scripts.package_kb -o kb_offline_bundle.tar.gz
    python -m scripts.package_kb -o kb_offline_bundle.tar.gz --dry-run
    python -m scripts.package_kb -o kb_offline_bundle.tar.gz --no-models
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_SCHEMA_CACHE = _BACKEND / "data" / "nci_schema_cache.json"

# Schema-stage embedding model (config default FIELD_MODEL). Bundled from the
# HuggingFace hub cache so the schema mapper loads it offline.
_SCHEMA_HF_DIR = "models--sentence-transformers--all-MiniLM-L6-v2"

# Alternate-framework weight files sentence-transformers (PyTorch) never loads
# when a ``model.safetensors`` is present — pure dead weight in an offline bundle.
_REDUNDANT_WEIGHTS = frozenset({
    "pytorch_model.bin", "flax_model.msgpack", "tf_model.h5", "rust_model.ot",
})


def _engine_export(dest: Path) -> None:
    """Invoke the engine's KB export CLI to produce kb.mhkb.tar.gz."""
    cmd = [
        sys.executable, "-m", "metaharmonizer.scripts.knowledge_db",
        "export", "-o", str(dest),
    ]
    subprocess.run(cmd, check=True)


def _corpus_csvs() -> list[Path]:
    """The corpus CSVs the engine reads at runtime (skip the large JSONs)."""
    from metaharmonizer._paths import RETRIEVED_ONTOLOGIES_DIR

    if not RETRIEVED_ONTOLOGIES_DIR.exists():
        return []
    return sorted(RETRIEVED_ONTOLOGIES_DIR.glob("*_corpus.csv"))


def _is_download_temp(path: Path, root: Path) -> bool:
    """True for HuggingFace incremental-download scratch (``.cache`` blobs and
    ``*.lock`` / ``*.metadata`` markers) — not needed for offline load."""
    rel_parts = path.relative_to(root).parts
    if ".cache" in rel_parts:
        return True
    return path.name.endswith((".lock", ".metadata"))


def _method_keys() -> set[str]:
    """Embedding-method directory names the engine actually loads (the keys of
    ``method_model.yaml``). Used to skip stray/duplicate model dirs — e.g. a
    manual ``sapbert_local`` copy the loader never reads. Read without importing
    torch. Empty set means "couldn't resolve" → bundle everything (safe)."""
    try:
        import yaml
        from importlib.util import find_spec

        spec = find_spec("metaharmonizer")
        locs = getattr(spec, "submodule_search_locations", None) if spec else None
        if locs:
            yml = Path(list(locs)[0]) / "models" / "method_model.yaml"
            if yml.exists():
                return set(yaml.safe_load(yml.read_text(encoding="utf-8")) or {})
    except Exception:
        pass
    return set()


def _model_cache_files() -> tuple[Path | None, list[Path]]:
    """Engine ontology models under ``MODEL_CACHE_DIR`` (e.g. ``sap-bert``).
    Keeps only dirs that map to a configured embedding method, drops HF download
    scratch, and prefers ``model.safetensors`` over the duplicate
    ``pytorch_model.bin``. Returns ``(root, files)``."""
    from metaharmonizer._paths import MODEL_CACHE_DIR

    if not MODEL_CACHE_DIR.exists():
        return None, []
    keys = _method_keys()
    files: list[Path] = []
    for p in MODEL_CACHE_DIR.rglob("*"):
        if not p.is_file() or _is_download_temp(p, MODEL_CACHE_DIR):
            continue
        top = p.relative_to(MODEL_CACHE_DIR).parts[0]
        if keys and top not in keys:
            continue  # stray/duplicate model dir — the loader never reads it
        if p.name in _REDUNDANT_WEIGHTS and (p.parent / "model.safetensors").exists():
            continue  # safetensors is preferred; other-framework weights are dead
        files.append(p)
    return MODEL_CACHE_DIR, files


def _hf_schema_model() -> tuple[Path | None, list[Path]]:
    """Schema embedding model (all-MiniLM-L6-v2) from the HuggingFace hub cache.
    Honours ``HF_HOME``; falls back to ``~/.cache/huggingface``. Returns
    ``(hub_root, files)`` where files are the model's snapshot tree."""
    import os

    hub_roots: list[Path] = []
    if os.getenv("HF_HOME"):
        hub_roots.append(Path(os.environ["HF_HOME"]) / "hub")
    hub_roots.append(Path.home() / ".cache" / "huggingface" / "hub")
    for root in hub_roots:
        model_dir = root / _SCHEMA_HF_DIR
        if model_dir.exists():
            files = [p for p in model_dir.rglob("*") if p.is_file()]
            return root, files
    return None, []


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.0f} GB"


def build_bundle(output: Path, *, with_models: bool = True, dry_run: bool = False) -> int:
    # Resolve everything first so --dry-run can report without exporting the KB.
    csvs = _corpus_csvs()
    if not csvs:
        print("[package] WARNING: no corpus CSVs found — a fresh instance "
              "will rebuild corpora from the network.", file=sys.stderr)

    mc_root, mc_files = (None, [])
    hf_root, hf_files = (None, [])
    if with_models:
        mc_root, mc_files = _model_cache_files()
        hf_root, hf_files = _hf_schema_model()
        if not mc_files:
            print("[package] WARNING: no engine model_cache found — ontology "
                  "matching will pull models from HuggingFace on first use.",
                  file=sys.stderr)
        if not hf_files:
            print("[package] WARNING: schema model (all-MiniLM-L6-v2) not found "
                  "in the HF cache — schema matching will pull it on first use.",
                  file=sys.stderr)

    if dry_run:
        mc_sz = sum(p.stat().st_size for p in mc_files)
        hf_sz = sum(p.stat().st_size for p in hf_files)
        cs_sz = sum(p.stat().st_size for p in csvs)
        print("[package] DRY RUN — would bundle:")
        print("  kb.mhkb.tar.gz          (engine KB export, size TBD)")
        print(f"  corpus CSVs             {len(csvs)} files, {_human(cs_sz)}")
        print(f"  nci_schema_cache.json   {'present' if _SCHEMA_CACHE.exists() else 'absent'}")
        print(f"  model_cache/            {len(mc_files)} files, {_human(mc_sz)}  (from {mc_root})")
        print(f"  hf_hub/{_SCHEMA_HF_DIR}  {len(hf_files)} files, {_human(hf_sz)}  (from {hf_root})")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        kb_archive = Path(tmp) / "kb.mhkb.tar.gz"
        print(f"[package] exporting engine KB -> {kb_archive.name}")
        _engine_export(kb_archive)

        output.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(output, "w:gz") as tar:
            tar.add(kb_archive, arcname="kb.mhkb.tar.gz")
            for csv in csvs:
                tar.add(csv, arcname=f"corpus/retrieved_ontologies/{csv.name}")
                print(f"[package] + corpus/{csv.name}")
            if _SCHEMA_CACHE.exists():
                tar.add(_SCHEMA_CACHE, arcname="nci_schema_cache.json")
                print(f"[package] + nci_schema_cache.json "
                      f"({_SCHEMA_CACHE.stat().st_size} bytes)")
            else:
                print("[package] note: no nci_schema_cache.json to bundle "
                      "(schema stage will warm on first use).")
            if mc_root and mc_files:
                for p in mc_files:
                    tar.add(p, arcname=f"model_cache/{p.relative_to(mc_root).as_posix()}")
                print(f"[package] + model_cache/ ({len(mc_files)} files, "
                      f"{_human(sum(p.stat().st_size for p in mc_files))})")
            if hf_root and hf_files:
                for p in hf_files:
                    tar.add(p, arcname=f"hf_hub/{p.relative_to(hf_root).as_posix()}")
                print(f"[package] + hf_hub/ ({len(hf_files)} files, "
                      f"{_human(sum(p.stat().st_size for p in hf_files))})")

    size = output.stat().st_size
    print(f"[package] wrote {output} ({_human(size)})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Package an offline KB bundle.")
    parser.add_argument("-o", "--output", required=True, type=Path,
                        help="Output bundle path (.tar.gz).")
    parser.add_argument("--no-models", action="store_true",
                        help="Omit the embedding models (smaller bundle).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be bundled without writing it.")
    args = parser.parse_args(argv)
    return build_bundle(args.output, with_models=not args.no_models, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
