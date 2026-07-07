"""Install an offline KB bundle produced by ``scripts.package_kb``.

Reverses the packaging: imports the engine KB into ``KNOWLEDGE_DB_DIR`` and
drops the corpus CSVs + warmed schema cache where the engine reads them, so the
first harmonization runs fully offline instead of re-downloading ontologies.

Usage::

    python -m scripts.seed_kb kb_offline_bundle.tar.gz [--force]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_SCHEMA_CACHE_DEST = _BACKEND / "data" / "nci_schema_cache.json"


def _align_data_dir_with_adapter() -> None:
    """Point ``METAHARMONIZER_DATA_DIR`` at ``backend/data`` when unset.

    Must mirror ``engine_adapter.metaharmonizer_impl._ensure_upstream_data_dir``:
    the running server relocates the engine's data root to ``backend/data`` when
    the bundled schema files live there, which also moves
    ``corpus/retrieved_ontologies/``. If seeding used the engine's *default*
    root (``~/.metaharmonizer``) the corpus would land where the server never
    looks, and the first harmonization would rebuild it from the network. Set
    the same env var here **before** importing ``metaharmonizer._paths`` so the
    corpus is installed where the server actually reads it.
    """
    if os.environ.get("METAHARMONIZER_DATA_DIR"):
        return
    backend_data = _BACKEND / "data"
    if (backend_data / "schema" / "ncit_descendants.json").exists():
        os.environ["METAHARMONIZER_DATA_DIR"] = str(backend_data)


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    """Extract with path-traversal protection (defense in depth)."""
    dest = dest.resolve()
    for member in tar.getmembers():
        target = (dest / member.name).resolve()
        if not str(target).startswith(str(dest)):
            raise RuntimeError(f"unsafe path in bundle: {member.name}")
    # filter="data" (py>=3.12) strips unsafe metadata; members already validated.
    tar.extractall(dest, filter="data")  # noqa: S202


def _import_kb(kb_archive: Path, force: bool) -> None:
    cmd = [
        sys.executable, "-m", "metaharmonizer.scripts.knowledge_db",
        "import", str(kb_archive),
    ]
    if force:
        cmd.append("--force")
    subprocess.run(cmd, check=True)


def seed(bundle: Path, *, force: bool) -> int:
    if not bundle.exists():
        print(f"[seed] bundle not found: {bundle}", file=sys.stderr)
        return 1

    _align_data_dir_with_adapter()
    from metaharmonizer._paths import RETRIEVED_ONTOLOGIES_DIR

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with tarfile.open(bundle, "r:gz") as tar:
            _safe_extract(tar, tmp_path)

        kb_archive = tmp_path / "kb.mhkb.tar.gz"
        if kb_archive.exists():
            print("[seed] importing engine KB ...")
            _import_kb(kb_archive, force)
        else:
            print("[seed] WARNING: no kb.mhkb.tar.gz in bundle", file=sys.stderr)

        # Corpus CSVs -> DATA_DIR so the engine loads instead of rebuilding.
        src_corpus = tmp_path / "corpus" / "retrieved_ontologies"
        if src_corpus.exists():
            RETRIEVED_ONTOLOGIES_DIR.mkdir(parents=True, exist_ok=True)
            for csv in sorted(src_corpus.glob("*_corpus.csv")):
                dst = RETRIEVED_ONTOLOGIES_DIR / csv.name
                if dst.exists() and not force:
                    print(f"[seed] exists, skipping (use --force): {dst.name}")
                    continue
                shutil.copy2(csv, dst)
                print(f"[seed] corpus -> {dst}")

        # Warmed schema cache -> backend/data so the schema stage starts warm.
        src_cache = tmp_path / "nci_schema_cache.json"
        if src_cache.exists():
            if _SCHEMA_CACHE_DEST.exists() and not force:
                print("[seed] schema cache exists, skipping (use --force)")
            else:
                _SCHEMA_CACHE_DEST.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_cache, _SCHEMA_CACHE_DEST)
                print(f"[seed] schema cache -> {_SCHEMA_CACHE_DEST}")

    print("[seed] done — instance is seeded for offline operation.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install an offline KB bundle.")
    parser.add_argument("bundle", type=Path, help="Path to kb_offline_bundle.tar.gz.")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing KB / corpus / cache.")
    args = parser.parse_args(argv)
    return seed(args.bundle, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
