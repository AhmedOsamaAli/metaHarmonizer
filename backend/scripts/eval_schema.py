r"""Schema-mapping benchmark harness (Sehyun's CPTAC source-tables → GDC, etc.).

Runs the REAL ``SchemaMapEngine`` over each provided source table against a
target schema preset (``gdc`` / ``cbio``) or an explicit target-schema CSV
(e.g. the SchemaRegistry's ``cmd_target_attrs.csv``), and reports, per table,
how many raw columns mapped and the stage distribution — plus a few example
column → field mappings.

Talks to the engine directly (scripts/ is outside the app import boundary), and
applies the app's startup patches so the SentenceTransformer is cached across
tables (no per-table model reload).

Usage (offline; schema models seeded)::

    cd backend
    $env:METAHARMONIZER_DATA_DIR="$PWD\data"; $env:HF_HUB_OFFLINE="1"; $env:TRANSFORMERS_OFFLINE="1"
    python -m scripts.eval_schema --tables ..\sehyun-input\source-tables\source-tables --schema gdc --out schema_gdc.csv
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd


def _is_match(v: object) -> bool:
    if v is None:
        return False
    s = str(v).strip().lower()
    return s not in ("", "nan", "none", "not found", "no match")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Benchmark schema mapping over source tables.")
    ap.add_argument("--tables", required=True, help="Directory of CSVs (or a glob).")
    ap.add_argument("--schema", default="gdc", help="Preset name: gdc | cbio (default: gdc).")
    ap.add_argument("--target-schema-path", default=None, help="Explicit target-schema CSV (overrides --schema).")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0, help="Max tables (0 = all).")
    ap.add_argument("--out", type=Path, default=None, help="Optional per-table summary CSV.")
    args = ap.parse_args(argv)
    try:  # avoid cp1252 UnicodeEncodeError when stdout is redirected to a file
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    p = Path(args.tables)
    files = sorted(p.glob("*.csv")) if p.is_dir() else sorted(Path().glob(args.tables))
    files = [f for f in files if not f.name.startswith("._")]
    if args.limit:
        files = files[: args.limit]
    if not files:
        print(f"[schema] no tables found at {args.tables}", file=sys.stderr)
        return 2

    target = args.target_schema_path or f"preset:{args.schema}"
    print(f"[schema] {len(files)} tables -> target {target} (top_k={args.top_k})")

    # Heavy import (torch); lazy so --help stays instant.
    from metaharmonizer import SchemaMapEngine  # noqa: E402  boundary-exempt tool

    from app.engine_adapter import _perf  # cache the SentenceTransformer across tables

    _perf.install_patches()

    summary: list[dict] = []
    details: list[dict] = []
    t_all = time.time()
    for f in files:
        t0 = time.time()
        try:
            kw = dict(top_k=args.top_k, mode="manual")
            if args.target_schema_path:
                eng = SchemaMapEngine(str(f), target_schema_path=args.target_schema_path, **kw)
            else:
                eng = SchemaMapEngine(str(f), args.schema, **kw)
            result = eng.run_schema_mapping()
        except Exception as exc:  # noqa: BLE001
            print(f"\n=== {f.name}: FAILED — {type(exc).__name__}: {exc}")
            continue
        recs = result.to_dict(orient="records") if result is not None else []
        n = len(recs)
        stages = Counter(str(r.get("stage")) for r in recs)
        mapped = sum(1 for r in recs if _is_match(r.get("match1")))

        def _score(r: dict) -> float:
            try:
                return float(r.get("match1_score") or 0)
            except (TypeError, ValueError):
                return 0.0

        # High-confidence = a Stage-1 exact/alias hit or score >= 0.9 (the band we
        # auto-accept). The rest is what a curator would review.
        high_conf = sum(1 for r in recs if str(r.get("stage")) == "stage1" or _score(r) >= 0.9)
        for r in recs:
            details.append({
                "table": f.name, "query": r.get("query"), "match1": r.get("match1"),
                "score": r.get("match1_score"), "stage": r.get("stage"), "match2": r.get("match2"),
            })
        elapsed = time.time() - t0
        print(f"\n=== {f.name}  ({n} columns, {elapsed:.1f}s) ===")
        print(f"  any-candidate: {mapped}/{n} ({mapped / (n or 1):.0%})   "
              f"high-conf (stage1/>=0.9): {high_conf}/{n} ({high_conf / (n or 1):.0%})   "
              f"stages: {dict(stages)}")
        for r in recs[:6]:
            print(
                f"    {str(r.get('query'))[:32]!r:>34} -> {r.get('match1')!r} "
                f"({r.get('match1_score')}, stage={r.get('stage')})"
            )
        row = {"table": f.name, "columns": n, "any_candidate": mapped, "high_conf": high_conf,
               "high_conf_pct": round(high_conf / (n or 1), 3), "seconds": round(elapsed, 1)}
        for k, v in stages.items():
            row[f"stage_{k}"] = v
        summary.append(row)

    if summary:
        tot_cols = sum(s["columns"] for s in summary)
        tot_map = sum(s["any_candidate"] for s in summary)
        tot_hc = sum(s["high_conf"] for s in summary)
        print("\n=== OVERALL ===")
        print(f"  tables: {len(summary)}   columns: {tot_cols}")
        print(f"  high-conf (stage1/>=0.9): {tot_hc}/{tot_cols} ({tot_hc / (tot_cols or 1):.0%})")
        print(f"  any-candidate produced : {tot_map}/{tot_cols} ({tot_map / (tot_cols or 1):.0%})")
        print(f"  total wall time: {time.time() - t_all:.1f}s")
        if args.out:
            pd.DataFrame(summary).to_csv(args.out, index=False)
            det = Path(str(args.out).replace(".csv", "_detail.csv"))
            pd.DataFrame(details).to_csv(det, index=False)
            print(f"  wrote {args.out} + {det}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
