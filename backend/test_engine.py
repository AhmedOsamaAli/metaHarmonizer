"""
Quick integration test for the SchemaMapEngine:
 - verifies stage distribution
 - verifies no score > 1.0
 - compares stage2 columns against the reference manual CSV
 - checks value_dict and alias_dict are loaded properly
"""
import sys, os, json, csv as csv_mod, logging

logging.disable(logging.WARNING)

BACKEND = os.path.dirname(os.path.abspath(__file__))
ENGINE  = os.path.join(BACKEND, "engine")
sys.path.insert(0, BACKEND)
sys.path.insert(0, ENGINE)
os.chdir(ENGINE)

from src.models.schema_mapper.engine import SchemaMapEngine

CSV = os.path.join(BACKEND, "data", "uploads", "new_meta_b3a3cd58.csv")
REF = os.path.join(ENGINE, "data", "schema_mapping_eval", "new_meta_manual.csv")

print("=" * 60)
print("Building engine …")
eng = SchemaMapEngine(CSV, mode="manual", top_k=5)
# NCI EVS API is enabled by default. Set SKIP_NCI_API=1 to bypass (offline/fast tests).
if os.getenv("SKIP_NCI_API", "").strip() in ("1", "true", "yes"):
    eng.nci_client.search_candidates = lambda *a, **kw: []
    print("NCI API: DISABLED (SKIP_NCI_API=1)")
else:
    print("NCI API: ENABLED (api-evsrest.nci.nih.gov)")

# ── Dictionary / value-dict status ──────────────────────────────────────────
print(f"\n[Dictionaries]")
print(f"  alias_dict loaded : {eng.has_alias_dict}")
print(f"  value_texts count : {len(eng.value_texts)}")
print(f"  value_embs shape  : {eng.value_embs.shape if eng.value_embs is not None else 'None'}")
print(f"  standard_fields   : {len(eng.standard_fields)}")

print("\nRunning schema mapping …")
result = eng.run_schema_mapping()

# ── Stage distribution ───────────────────────────────────────────────────────
stage_counts = result["stage"].value_counts().to_dict()
print(f"\n[Stage distribution]")
for s, n in sorted(stage_counts.items()):
    print(f"  {s:12s}: {n}")

# ── Score sanity – no score > 1.0 ───────────────────────────────────────────
all_over = result[result["match1_score"].fillna(0) > 1.0]
print(f"\n[Score > 1.0]  {len(all_over)} rows (should be 0)")
if not all_over.empty:
    print(all_over[["query", "stage", "match1", "match1_score", "method"]].to_string())

# ── Stage 2 details ──────────────────────────────────────────────────────────
s2 = result[result["stage"] == "stage2"]
print(f"\n[Stage 2 mappings]  {len(s2)} rows")
if not s2.empty:
    print(s2[["query", "match1", "match1_score", "method"]].to_string())

# ── Stage 3 details (check treatment columns) ────────────────────────────────
s3 = result[result["stage"] == "stage3"]
print(f"\n[Stage 3 mappings]  {len(s3)} rows  (max score: {s3['match1_score'].max():.4f})")
print(s3[["query", "match1", "match1_score", "method"]].head(10).to_string())

# ── Compare against reference manual CSV ─────────────────────────────────────
print(f"\n[Comparison vs reference {os.path.basename(REF)}]")
ref = {}
with open(REF, newline="", encoding="utf-8") as fh:
    for row in csv_mod.DictReader(fh):
        q = row["query"].strip()
        m1 = row["match1"].strip()
        if m1:
            ref[q] = m1

our = {str(r["query"]): str(r["match1"]) for _, r in result.iterrows()
       if str(r.get("match1", "")) not in ("", "nan", "None")}

tp = fp = fn = 0
mismatches = []
for col, gold in ref.items():
    pred = our.get(col)
    if pred and pred == gold:
        tp += 1
    elif pred and pred != gold:
        fp += 1
        mismatches.append((col, gold, pred))
    else:
        fn += 1
        mismatches.append((col, gold, "(unmapped)"))

precision = tp / (tp + fp) if (tp + fp) else 0.0
recall    = tp / (tp + fn) if (tp + fn) else 0.0
f1        = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

print(f"  TP={tp}  FP={fp}  FN={fn}")
print(f"  Precision={precision:.3f}  Recall={recall:.3f}  F1={f1:.3f}")
print(f"\n  First 20 mismatches / unmapped:")
for col, gold, pred in mismatches[:20]:
    print(f"    {col:40s}  gold={gold:30s}  pred={pred}")

print("\n" + "=" * 60)
print("DONE")
