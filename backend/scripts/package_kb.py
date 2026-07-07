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

Install it with ``scripts/seed_kb.py``.

Usage::

    python -m scripts.package_kb -o kb_offline_bundle.tar.gz
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


def build_bundle(output: Path) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        kb_archive = Path(tmp) / "kb.mhkb.tar.gz"
        print(f"[package] exporting engine KB -> {kb_archive.name}")
        _engine_export(kb_archive)

        csvs = _corpus_csvs()
        if not csvs:
            print("[package] WARNING: no corpus CSVs found — a fresh instance "
                  "will rebuild corpora from the network.", file=sys.stderr)

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

    size = output.stat().st_size
    print(f"[package] wrote {output} ({size} bytes)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Package an offline KB bundle.")
    parser.add_argument("-o", "--output", required=True, type=Path,
                        help="Output bundle path (.tar.gz).")
    args = parser.parse_args(argv)
    return build_bundle(args.output)


if __name__ == "__main__":
    raise SystemExit(main())
