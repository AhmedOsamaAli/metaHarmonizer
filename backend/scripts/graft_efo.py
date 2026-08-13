"""Graft the un-rebuildable extras from an existing bundle into a freshly-built KB.

``build_kb`` only builds the fetchable launch tuples (disease/ncit,
bodysite/uberon, treatment/ncit). **EFO / phenotype** is a hand-merged corpus
whose codes aren't OLS-fetchable and which ships no concept table, so
``build_kb`` cannot regenerate it — it must be carried forward from the current
bundle.

The warmed ``nci_schema_cache.json`` is deliberately **not** carried: it maps
value -> NCiT code and a cache hit returns the stored code without re-fetching,
so a stale entry would outlive a KB refresh. Instances re-warm it fresh.

Run this AFTER ``build_kb`` and BEFORE ``package_kb`` so the repackaged bundle
refreshes the fetchable ontologies while preserving EFO.

    python -m scripts.graft_efo --from-bundle <current_kb_offline_bundle.tar.gz>

Build tooling (not app runtime), so importing the engine's ``_paths`` is fine —
the engine-adapter boundary only governs ``backend/app``.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from pathlib import Path


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    dest = dest.resolve()
    for m in tar.getmembers():
        if not str((dest / m.name).resolve()).startswith(str(dest)):
            raise RuntimeError(f"unsafe path in bundle: {m.name}")
    tar.extractall(dest, filter="data")  # noqa: S202 — members validated above


def _find(root: Path, name: str) -> Path | None:
    hit = next(iter(sorted(root.rglob(name))), None)
    return hit


def _copy_efo_tables(old_db: Path, new_db: Path) -> None:
    """Copy every ``efo_*`` table from the old KB's sqlite into the fresh one."""
    con = sqlite3.connect(str(new_db))
    try:
        con.execute("ATTACH ? AS old", (str(old_db),))
        tables = [
            r[0] for r in con.execute(
                "SELECT name FROM old.sqlite_master WHERE type='table' AND name LIKE 'efo\\_%' ESCAPE '\\'"
            )
        ]
        for t in tables:
            con.execute(f'DROP TABLE IF EXISTS main."{t}"')
            con.execute(f'CREATE TABLE main."{t}" AS SELECT * FROM old."{t}"')
            n = con.execute(f'SELECT count(*) FROM main."{t}"').fetchone()[0]
            print(f"[graft] EFO table {t}: {n} row(s)")
        con.commit()
        if not tables:
            print("[graft] WARNING: no efo_* tables in the source KB")
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from-bundle", required=True, help="current published bundle to graft EFO + cache from")
    args = ap.parse_args(argv)

    from metaharmonizer._paths import (  # noqa: E402
        FAISS_INDEX_DIR,
        RETRIEVED_ONTOLOGIES_DIR,
        VECTOR_DB_PATH,
    )

    src = Path(args.from_bundle)
    if not src.exists():
        print(f"[graft] source bundle not found: {src}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with tarfile.open(src, "r:gz") as t:
            _safe_extract(t, tmp_path)

        # 1. EFO corpus CSV -> the dir the engine loads corpora from.
        efo_csv = tmp_path / "corpus" / "retrieved_ontologies" / "efo_phenotype_corpus.csv"
        if efo_csv.exists():
            RETRIEVED_ONTOLOGIES_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(efo_csv, RETRIEVED_ONTOLOGIES_DIR / efo_csv.name)
            print(f"[graft] EFO corpus -> {RETRIEVED_ONTOLOGIES_DIR / efo_csv.name}")
        else:
            print("[graft] WARNING: no efo_phenotype_corpus.csv in source bundle")

        # 2. The warmed schema cache is intentionally NOT carried forward: it
        #    maps value -> NCiT code, and a cache hit returns the stored code
        #    without re-fetching, so a stale entry would outlive a KB refresh.
        #    The instance re-warms it fresh against the new KB at runtime.

        # 3. EFO KB artifacts (FAISS index + sqlite tables) from the engine archive.
        kb_archive = tmp_path / "kb.mhkb.tar.gz"
        if not kb_archive.exists():
            print("[graft] WARNING: no kb.mhkb.tar.gz in bundle; EFO KB not grafted")
            return 0
        kb_tmp = tmp_path / "_kb"
        kb_tmp.mkdir()
        with tarfile.open(kb_archive, "r:gz") as t:
            _safe_extract(t, kb_tmp)

        old_faiss_dir = _find(kb_tmp, "faiss_indexes")
        if old_faiss_dir:
            FAISS_INDEX_DIR.mkdir(parents=True, exist_ok=True)
            grafted = 0
            for f in sorted(old_faiss_dir.glob("st_*_efo_phenotype.index*")):
                shutil.copy2(f, FAISS_INDEX_DIR / f.name)
                grafted += 1
            print(f"[graft] EFO FAISS index files: {grafted}")

        old_db = _find(kb_tmp, "vector_db.sqlite")
        if old_db and VECTOR_DB_PATH.exists():
            _copy_efo_tables(old_db, VECTOR_DB_PATH)
        elif not VECTOR_DB_PATH.exists():
            print(f"[graft] WARNING: fresh KB has no {VECTOR_DB_PATH}; run build_kb first", file=sys.stderr)

    print("[graft] done — EFO + schema cache grafted into the fresh KB.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
