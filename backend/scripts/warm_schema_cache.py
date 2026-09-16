"""Warm the schema model and persistent NCI lookup cache for offline packaging."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd

_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent
_CACHE = _BACKEND / "data/nci_schema_cache.json"
_DEFAULT_SAMPLE = _REPO / "metadata_samples/new_meta.csv"


def warm(sample: Path) -> int:
    if not sample.is_file():
        print(f"[schema-cache] sample not found: {sample}")
        return 1

    os.environ.setdefault("METAHARMONIZER_DATA_DIR", str(_BACKEND / "data"))
    from app.engine_adapter.metaharmonizer_impl import MetaHarmonizerAdapter

    frame = pd.read_csv(sample, dtype=str)
    adapter = MetaHarmonizerAdapter(mode="manual")
    rows = adapter.harmonize_schema(frame, pd.DataFrame(), csv_path=str(sample))
    if not rows:
        print("[schema-cache] schema engine returned no rows")
        return 1
    if not _CACHE.is_file() or _CACHE.stat().st_size == 0:
        print(f"[schema-cache] cache was not written: {_CACHE}")
        return 1
    print(f"[schema-cache] warmed {_CACHE} with {len(rows)} mapped columns")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=Path, default=_DEFAULT_SAMPLE)
    args = parser.parse_args(argv)
    return warm(args.sample)


if __name__ == "__main__":
    raise SystemExit(main())
