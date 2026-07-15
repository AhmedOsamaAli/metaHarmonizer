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


def _hf_hub_root() -> Path:
    """The HuggingFace hub cache root to install the schema model into.
    Honours ``HF_HOME``; falls back to ``~/.cache/huggingface``."""
    if os.environ.get("HF_HOME"):
        return Path(os.environ["HF_HOME"]) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def _install_tree(src_root: Path, dst_root: Path, force: bool, *, label: str) -> None:
    """Copy a bundled directory tree into ``dst_root``, preserving layout.
    Existing files are kept unless ``--force`` (models are immutable, so a
    present tree is normally already correct)."""
    if not src_root.exists():
        return
    files = [p for p in src_root.rglob("*") if p.is_file()]
    if not files:
        return
    copied = 0
    for p in files:
        dst = dst_root / p.relative_to(src_root)
        if dst.exists() and not force:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
        copied += 1
    if copied:
        print(f"[seed] {label}: installed {copied} file(s) -> {dst_root}")
    else:
        print(f"[seed] {label}: already present at {dst_root} (use --force to overwrite)")


def _download(url: str, dest: Path, *, sha256: str | None = None) -> None:
    """Stream the bundle from ``url`` to ``dest`` (atomic, optional sha256 check).

    Standard-library only, so it works in a bare container with no extra deps.
    Writes to a ``.part`` file and renames on success, so an interrupted run
    never leaves a half-written bundle that looks complete.
    """
    import hashlib
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    print(f"[seed] downloading bundle from {url}")
    digest = hashlib.sha256()
    done = 0
    req = urllib.request.Request(url, headers={"User-Agent": "metaharmonizer-seed-kb"})
    with urllib.request.urlopen(req) as resp, open(tmp, "wb") as fh:  # noqa: S310
        total = int(resp.headers.get("Content-Length") or 0)
        while True:
            chunk = resp.read(1 << 20)  # 1 MiB
            if not chunk:
                break
            fh.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if total:
                print(
                    f"\r[seed]   {done // (1 << 20)}/{total // (1 << 20)} MiB "
                    f"({done * 100 // total}%)",
                    end="",
                    flush=True,
                )
    if total:
        print()
    if sha256 and digest.hexdigest().lower() != sha256.strip().lower():
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"bundle sha256 mismatch: expected {sha256}, got {digest.hexdigest()}"
        )
    tmp.replace(dest)
    print(f"[seed] downloaded {done // (1 << 20)} MiB -> {dest}")


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

        # Engine ontology models (e.g. sap-bert) -> MODEL_CACHE_DIR, so the
        # ontology stage loads embeddings from disk under HF_HUB_OFFLINE=1.
        from metaharmonizer._paths import MODEL_CACHE_DIR

        _install_tree(tmp_path / "model_cache", MODEL_CACHE_DIR, force, label="model")

        # Schema model (all-MiniLM-L6-v2) -> HuggingFace hub cache.
        _install_tree(tmp_path / "hf_hub", _hf_hub_root(), force, label="hf-model")

    print("[seed] done — instance is seeded for offline operation.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install an offline KB bundle, downloading it first when missing."
    )
    parser.add_argument(
        "bundle",
        nargs="?",
        default=os.getenv("KB_BUNDLE_PATH", "kb_offline_bundle.tar.gz"),
        help="Local path to the bundle (downloaded here when missing). May also be an http(s) URL.",
    )
    parser.add_argument(
        "--url",
        default=os.getenv("KB_BUNDLE_URL"),
        help="Download the bundle from this URL when the local file is missing (default: $KB_BUNDLE_URL).",
    )
    parser.add_argument(
        "--sha256",
        default=os.getenv("KB_BUNDLE_SHA256"),
        help="Expected sha256 for an integrity check (default: $KB_BUNDLE_SHA256).",
    )
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing KB / corpus / cache / models.")
    args = parser.parse_args(argv)

    # The positional may be a URL directly (convenience).
    url = args.url
    bundle_arg = str(args.bundle)
    if bundle_arg.startswith(("http://", "https://")):
        url = bundle_arg
        bundle = Path(os.getenv("KB_BUNDLE_PATH", "kb_offline_bundle.tar.gz"))
    else:
        bundle = Path(bundle_arg)

    if not bundle.exists():
        if url:
            _download(url, bundle, sha256=args.sha256)
        else:
            print(
                f"[seed] bundle not found and no --url / $KB_BUNDLE_URL to download it: {bundle}",
                file=sys.stderr,
            )
            return 1
    return seed(bundle, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
