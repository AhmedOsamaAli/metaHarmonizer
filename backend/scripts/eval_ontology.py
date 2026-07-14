"""Ontology-mapping evaluation harness (Sehyun's om_benchmark_* sets).

Runs the REAL ``OntoMapEngine`` over a benchmark's ``query`` column and scores
its top match against the ground-truth ``ref_match`` / ``ref_match_id``.

The benchmarks are EFO-referenced while our disease corpus is NCIt, so raw
**id** equality is not apples-to-apples across ontologies — the headline metric
is **label match** (did the engine land on the right concept name, normalized).
An ``id`` match column is still reported for same-ontology runs.

Usage (offline; needs the disease NCIt corpus + sap-bert already seeded)::

    cd backend
    $env:METAHARMONIZER_DATA_DIR="$PWD\data"; $env:KNOWLEDGE_DB_DIR="$PWD\kb_build"
    $env:HF_HUB_OFFLINE="1"; $env:TRANSFORMERS_OFFLINE="1"
    python -m scripts.eval_ontology --benchmark ..\sehyun-input\om_benchmark_ols_efo_disease.csv \
        --category disease --source ncit --limit 100 --out eval_disease.csv

This is a benchmarking tool: like scripts/kb_probe.py it talks to the engine
directly (scripts/ is outside the app import boundary).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd


def _norm(s: object) -> str:
    """Normalize a label for comparison: lowercase, collapse whitespace, strip
    surrounding punctuation the ontologies differ on."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    text = str(s).strip().lower()
    return " ".join(text.split())


def _first(raw: dict, *keys: str):
    for k in keys:
        v = raw.get(k)
        if v is not None and not (isinstance(v, float) and pd.isna(v)):
            return v
    return None


def _load_corpus_codes(category: str, source: str) -> dict[str, str]:
    """Build a normalized ``label -> code`` map for a corpus.

    ``OntoMapEngine.run()`` returns only the matched *label*, never the code, so
    the id metric needs the code recovered from the corpus the engine searched
    (exactly what the production adapter does). Handles both corpus column
    conventions: ``label``/``obo_id`` (NCIt/UBERON) and
    ``official_label``/``clean_code`` (EFO). Returns ``{}`` if unreadable.
    """
    import os

    env = os.environ.get("METAHARMONIZER_DATA_DIR")
    base = Path(env) if env else Path(__file__).resolve().parents[1] / "data"
    path = base / "corpus" / "retrieved_ontologies" / f"{source}_{category}_corpus.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    label_col = next((c for c in ("label", "official_label") if c in df.columns), None)
    code_col = next((c for c in ("obo_id", "clean_code") if c in df.columns), None)
    if not label_col or not code_col:
        return {}
    out: dict[str, str] = {}
    for lab, code in zip(df[label_col], df[code_col]):
        if not isinstance(lab, str):
            continue
        key = _norm(lab)
        val = "" if code is None else str(code).strip()
        if key and val and key not in out:  # first-wins for stability
            out[key] = val
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evaluate ontology mapping against a benchmark CSV.")
    ap.add_argument("--benchmark", required=True, type=Path, help="CSV with query,ref_match,ref_match_id.")
    ap.add_argument("--category", default="disease", help="OntoMapEngine corpus category (default: disease).")
    ap.add_argument("--source", default="ncit", help="Ontology source (default: ncit).")
    ap.add_argument("--limit", type=int, default=100, help="Max distinct queries to evaluate (0 = all).")
    ap.add_argument("--s2-method", default="sap-bert")
    ap.add_argument("--raw", action="store_true",
                    help="Skip the app's exact-match correctness patch (benchmark upstream as-is).")
    ap.add_argument("--no-concept-tables", action="store_true",
                    help="Skip the OLS-dependent concept-table build and synonym stage 2.5 "
                         "(measure stage-1+2 only). Use when the concept table isn't available "
                         "offline, e.g. the EFO merged corpus whose codes aren't OLS-fetchable.")
    ap.add_argument("--out", type=Path, default=None, help="Optional per-row results CSV.")
    args = ap.parse_args(argv)

    if not args.benchmark.exists():
        print(f"[eval] benchmark not found: {args.benchmark}", file=sys.stderr)
        return 2

    bench = pd.read_csv(args.benchmark)
    needed = {"query", "ref_match"}
    if not needed.issubset(bench.columns):
        print(f"[eval] benchmark must have columns {needed}; got {list(bench.columns)}", file=sys.stderr)
        return 2

    # One row per distinct query (keep the first ground-truth mapping).
    bench = bench.dropna(subset=["query"]).drop_duplicates(subset=["query"], keep="first")
    if args.limit and args.limit > 0:
        bench = bench.head(args.limit)
    queries = [str(q) for q in bench["query"].tolist()]
    gold_label = {str(r["query"]): r.get("ref_match") for _, r in bench.iterrows()}
    gold_id = {str(r["query"]): r.get("ref_match_id") for _, r in bench.iterrows()}
    print(f"[eval] {len(queries)} distinct queries from {args.benchmark.name} "
          f"-> {args.category}/{args.source} via {args.s2_method}")

    # Engine is heavy to import (torch); do it lazily so --help stays instant.
    from metaharmonizer import OntoMapEngine  # noqa: E402  benchmark tool, boundary-exempt

    # Apply the same exact-match correctness patch the app installs at startup,
    # so the benchmark reflects real production behaviour (unless --raw).
    if not args.raw:
        from app.engine_adapter._perf import patch_exact_matching

        patch_exact_matching()

    engine_kwargs: dict = {}
    if args.no_concept_tables:
        # Benchmark tool (boundary-exempt): the EFO merged corpus ships no concept
        # table (efo_phenotype.json) and its codes aren't OLS-fetchable, so the
        # setup-time build fails offline. Neutralize it and the synonym stage so
        # stage-1+2 (exact + SapBERT semantic) run standalone. This is a fair
        # lower bound on quality (no synonym boost).
        OntoMapEngine._ensure_concept_tables = lambda self, corpus_df: None
        engine_kwargs["skip_stage25"] = True
        print("[eval] concept tables + synonym stage 2.5 DISABLED (stage-1+2 only)")

    t0 = time.time()
    engine = OntoMapEngine(
        corpus_category=args.category,
        query_ls=queries,
        ontology_source=args.source,
        s2_method=args.s2_method,
        s2_strategy="st",
        **engine_kwargs,
    )
    result = engine.run()
    elapsed = time.time() - t0
    print(f"[eval] engine.run() over {len(queries)} queries in {elapsed:.1f}s")

    # The engine emits labels but no code; recover the code from the corpus by
    # label so the id metric is real (mirrors the production adapter).
    code_map = _load_corpus_codes(args.category, args.source)
    if code_map:
        print(f"[eval] corpus code map: {len(code_map)} labels for id recovery")

    records = result.to_dict(orient="records") if result is not None else []
    rows: list[dict] = []
    label_hits = idmatch = predicted = 0
    for raw in records:
        q = str(raw.get("query"))
        pred_term = _first(raw, "match1")
        pred_id = _first(raw, "match1_id", "match1_obo_id", "obo_id")
        if not pred_id and pred_term and code_map:
            pred_id = code_map.get(_norm(pred_term))
        score = _first(raw, "match1_score") or 0.0
        gl, gi = gold_label.get(q), gold_id.get(q)
        label_hit = bool(pred_term) and _norm(pred_term) == _norm(gl)
        id_hit = bool(pred_id) and gi is not None and str(pred_id) == str(gi)
        if pred_term:
            predicted += 1
        label_hits += int(label_hit)
        idmatch += int(id_hit)
        rows.append({
            "query": q, "gold": gl, "predicted": pred_term, "pred_id": pred_id,
            "score": round(float(score), 4), "label_hit": label_hit, "id_hit": id_hit,
        })

    n = len(rows) or 1
    print("\n=== RESULTS ===")
    print(f"  queries evaluated : {len(rows)}")
    print(f"  produced a match  : {predicted}/{len(rows)} ({predicted / n:.1%})")
    print(f"  LABEL match (top-1): {label_hits}/{len(rows)} ({label_hits / n:.1%})")
    print(f"  id match (same-ontology only): {idmatch}/{len(rows)} ({idmatch / n:.1%})")

    if args.out:
        pd.DataFrame(rows).to_csv(args.out, index=False)
        print(f"[eval] per-row results -> {args.out}")
    # Show a few misses to eyeball quality.
    misses = [r for r in rows if not r["label_hit"] and r["predicted"]][:8]
    if misses:
        print("\n  sample mismatches (query -> predicted | gold):")
        for r in misses:
            print(f"    {r['query'][:40]:<40} -> {str(r['predicted'])[:32]:<32} | {str(r['gold'])[:32]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
