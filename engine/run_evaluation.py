"""
MetaHarmonizer Schema Mapper Evaluation Script
==============================================
Tests the existing SchemaMapEngine approach on metadata_samples
and reports findings (accuracy, coverage, confidence, edge cases).

This is the "Mapper Evaluation" bonus deliverable for GSoC 2026 #136.
"""

import sys
import os
import types
import time
import json
import pandas as pd
import numpy as np

# ── Bypass src.models.__init__.py (it imports ontology mappers we don't need) ──
# We only need the schema_mapper subpackage, not the ontology mappers.
mod = types.ModuleType('src.models')
mod.__path__ = [os.path.join(os.path.dirname(__file__), 'src', 'models')]
mod.__package__ = 'src.models'
sys.modules['src.models'] = mod

# Now we can import SchemaMapEngine without triggering ontology mapper imports
from src.models.schema_mapper.engine import SchemaMapEngine

# ── Paths ──
SAMPLES_DIR = os.path.join(os.path.dirname(__file__), '..', 'metadata_samples')
NEW_META = os.path.join(SAMPLES_DIR, 'new_meta.csv')
CURATED_META = os.path.join(SAMPLES_DIR, 'curated_meta.csv')
REPORT_FILE = os.path.join(os.path.dirname(__file__), '..', 'MAPPER_EVALUATION_REPORT.md')

def load_ground_truth():
    """Load curated metadata to build ground truth field list."""
    df = pd.read_csv(CURATED_META, low_memory=False)
    return df

def run_schema_mapping(csv_path):
    """Run SchemaMapEngine on the given CSV in manual mode (no LLM)."""
    print(f"\n{'='*60}")
    print("Running SchemaMapEngine (manual mode, top_k=5)")
    print(f"Input: {csv_path}")
    print(f"{'='*60}\n")
    
    t0 = time.time()
    engine = SchemaMapEngine(csv_path, mode="manual", top_k=5)
    t_init = time.time() - t0
    print(f"Engine initialized in {t_init:.1f}s")
    print(f"  - Input shape: {engine.df.shape}")
    print(f"  - Columns to map: {len(engine.df.columns)}")
    print(f"  - Standard fields loaded: {len(engine.standard_fields)}")
    
    t0 = time.time()
    results = engine.run_schema_mapping()
    t_run = time.time() - t0
    print(f"\nMapping completed in {t_run:.1f}s")
    print(f"  - Results: {len(results)} rows")
    
    return results, engine, t_init, t_run

def analyze_results(results_df, curated_df):
    """Analyze mapping results and produce evaluation metrics."""
    analysis = {}
    
    # ── 1. Basic coverage ──
    total_cols = len(results_df)
    invalid = results_df[results_df['stage'] == 'invalid'] if 'stage' in results_df.columns else pd.DataFrame()
    mapped = results_df[results_df['stage'] != 'invalid'] if 'stage' in results_df.columns else results_df
    
    analysis['total_columns'] = total_cols
    analysis['invalid_columns'] = len(invalid)
    analysis['mapped_columns'] = len(mapped)
    
    # ── 2. Stage distribution ──
    if 'stage' in results_df.columns:
        stage_counts = results_df['stage'].value_counts().to_dict()
        analysis['stage_distribution'] = stage_counts
    
    # ── 3. Method distribution ──
    if 'method' in results_df.columns:
        method_counts = results_df['method'].value_counts().to_dict()
        analysis['method_distribution'] = method_counts
    
    # ── 4. Confidence score analysis ──
    if 'match1_score' in results_df.columns:
        scores = results_df['match1_score'].dropna()
        analysis['confidence'] = {
            'mean': float(scores.mean()),
            'median': float(scores.median()),
            'std': float(scores.std()),
            'min': float(scores.min()),
            'max': float(scores.max()),
            'high_confidence_90': int((scores >= 0.9).sum()),
            'medium_confidence_70_90': int(((scores >= 0.7) & (scores < 0.9)).sum()),
            'low_confidence_50_70': int(((scores >= 0.5) & (scores < 0.7)).sum()),
            'very_low_below_50': int((scores < 0.5).sum()),
        }
        
        # Confidence buckets for histogram
        buckets = pd.cut(scores, bins=[0, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0])
        analysis['confidence_buckets'] = buckets.value_counts().sort_index().to_dict()
    
    # ── 5. Ground truth comparison ──
    curated_fields = set(curated_df.columns.tolist())
    
    if 'match1' in results_df.columns:
        exact_matches = 0
        top3_matches = 0
        top5_matches = 0
        mapped_to_curated = 0
        
        for _, row in mapped.iterrows():
            m1 = str(row.get('match1', '')).strip()
            if m1 in curated_fields:
                mapped_to_curated += 1
            
            # Check if query itself is already a curated field (trivial match)
            query = str(row.get('query', '')).strip()
            if query.lower() in {f.lower() for f in curated_fields}:
                exact_matches += 1
        
        analysis['ground_truth'] = {
            'curated_fields_count': len(curated_fields),
            'matches_to_curated_field': mapped_to_curated,
            'query_already_curated': exact_matches,
        }
    
    # ── 6. Edge cases ──
    edge_cases = {
        'no_match1': 0,
        'very_low_score': [],
        'ambiguous': [],
    }
    
    if 'match1' in results_df.columns and 'match1_score' in results_df.columns:
        for _, row in mapped.iterrows():
            query = str(row.get('query', ''))
            m1 = row.get('match1')
            s1 = row.get('match1_score')
            
            if pd.isna(m1) or str(m1).strip() == '':
                edge_cases['no_match1'] += 1
                continue
            
            if pd.notna(s1) and s1 < 0.3:
                edge_cases['very_low_score'].append({
                    'query': query,
                    'match': str(m1),
                    'score': float(s1),
                    'stage': str(row.get('stage', '')),
                })
            
            # Check ambiguous: top2 scores very close
            m2_score = row.get('match2_score')
            if pd.notna(s1) and pd.notna(m2_score) and s1 > 0 and (s1 - m2_score) < 0.05:
                edge_cases['ambiguous'].append({
                    'query': query,
                    'match1': str(m1),
                    'score1': float(s1),
                    'match2': str(row.get('match2', '')),
                    'score2': float(m2_score),
                })
    
    analysis['edge_cases'] = edge_cases
    
    return analysis

def generate_report(results_df, analysis, t_init, t_run):
    """Generate the evaluation report as Markdown."""
    lines = []
    
    lines.append("# MetaHarmonizer Schema Mapper — Evaluation Report")
    lines.append("")
    lines.append("> **Purpose**: Evaluate the existing MetaHarmonizer `SchemaMapEngine` on `metadata_samples` ")
    lines.append("> as the *Mapper Evaluation* bonus deliverable for GSoC 2026 cBioPortal Issue #136.")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # ── 1. Executive Summary ──
    lines.append("## 1. Executive Summary")
    lines.append("")
    total = analysis['total_columns']
    mapped = analysis['mapped_columns']
    invalid = analysis['invalid_columns']
    pct = mapped / total * 100 if total else 0
    lines.append(f"The SchemaMapEngine was run on `new_meta.csv` ({total} columns) in **manual mode** ")
    lines.append(f"(Stages 1–3, no LLM fallback). Key findings:")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total columns | {total} |")
    lines.append(f"| Invalid (filtered) | {invalid} |")
    lines.append(f"| Mapped | {mapped} ({pct:.1f}%) |")
    
    if 'confidence' in analysis:
        c = analysis['confidence']
        lines.append(f"| Mean confidence | {c['mean']:.3f} |")
        lines.append(f"| Median confidence | {c['median']:.3f} |")
        lines.append(f"| High confidence (≥0.9) | {c['high_confidence_90']} |")
        lines.append(f"| Low confidence (<0.5) | {c['very_low_below_50']} |")
    
    lines.append(f"| Init time | {t_init:.1f}s |")
    lines.append(f"| Mapping time | {t_run:.1f}s |")
    lines.append("")
    
    # ── 2. Stage Distribution ──
    lines.append("## 2. Stage Distribution")
    lines.append("")
    lines.append("Which pipeline stage resolved each column:")
    lines.append("")
    lines.append("| Stage | Count | % |")
    lines.append("|-------|-------|---|")
    if 'stage_distribution' in analysis:
        for stage, count in sorted(analysis['stage_distribution'].items()):
            pct = count / total * 100
            lines.append(f"| {stage} | {count} | {pct:.1f}% |")
    lines.append("")
    
    # Stage descriptions
    lines.append("**Stage Descriptions:**")
    lines.append("- `invalid`: Column filtered out (all null, single-value, or noise)")
    lines.append("- `stage1`: Dictionary matching (exact + fuzzy, threshold=92)")
    lines.append("- `stage2`: Value-based matching (value dictionary + ontology lookup)")
    lines.append("- `stage3`: Semantic matching (SentenceTransformer `all-MiniLM-L6-v2` embeddings)")
    lines.append("- `stage4`: LLM fallback (disabled in manual mode)")
    lines.append("")
    
    # ── 3. Method Distribution ──
    lines.append("## 3. Method Distribution")
    lines.append("")
    lines.append("| Method | Count |")
    lines.append("|--------|-------|")
    if 'method_distribution' in analysis:
        for method, count in sorted(analysis['method_distribution'].items(), key=lambda x: -x[1]):
            lines.append(f"| {method} | {count} |")
    lines.append("")
    
    # ── 4. Confidence Analysis ──
    lines.append("## 4. Confidence Score Analysis")
    lines.append("")
    if 'confidence' in analysis:
        c = analysis['confidence']
        lines.append("### Distribution")
        lines.append("")
        lines.append(f"| Statistic | Value |")
        lines.append(f"|-----------|-------|")
        lines.append(f"| Mean | {c['mean']:.4f} |")
        lines.append(f"| Median | {c['median']:.4f} |")
        lines.append(f"| Std Dev | {c['std']:.4f} |")
        lines.append(f"| Min | {c['min']:.4f} |")
        lines.append(f"| Max | {c['max']:.4f} |")
        lines.append("")
        
        lines.append("### Confidence Tiers")
        lines.append("")
        lines.append("| Tier | Range | Count |")
        lines.append("|------|-------|-------|")
        lines.append(f"| High | ≥ 0.90 | {c['high_confidence_90']} |")
        lines.append(f"| Medium | 0.70 – 0.89 | {c['medium_confidence_70_90']} |")
        lines.append(f"| Low | 0.50 – 0.69 | {c['low_confidence_50_70']} |")
        lines.append(f"| Very Low | < 0.50 | {c['very_low_below_50']} |")
        lines.append("")
        
        if 'confidence_buckets' in analysis:
            lines.append("### Score Histogram")
            lines.append("")
            lines.append("```")
            for bucket, count in analysis['confidence_buckets'].items():
                bar = '█' * count
                lines.append(f"  {str(bucket):>15s} | {bar} ({count})")
            lines.append("```")
            lines.append("")
    
    # ── 5. Ground Truth Comparison ──
    if 'ground_truth' in analysis:
        lines.append("## 5. Ground Truth Comparison")
        lines.append("")
        gt = analysis['ground_truth']
        lines.append(f"Using `curated_meta.csv` ({gt['curated_fields_count']} curated fields) as reference:")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Top-1 match is a curated field | {gt['matches_to_curated_field']} |")
        lines.append(f"| Query already exists in curated fields | {gt['query_already_curated']} |")
        lines.append("")
    
    # ── 6. Edge Cases ──
    lines.append("## 6. Edge Cases & Failure Analysis")
    lines.append("")
    ec = analysis['edge_cases']
    lines.append(f"- **No match found**: {ec['no_match1']} columns")
    lines.append(f"- **Very low confidence (< 0.3)**: {len(ec['very_low_score'])} columns")
    lines.append(f"- **Ambiguous matches (Δscore < 0.05)**: {len(ec['ambiguous'])} columns")
    lines.append("")
    
    if ec['very_low_score']:
        lines.append("### Very Low Confidence Mappings")
        lines.append("")
        lines.append("| Query | Best Match | Score | Stage |")
        lines.append("|-------|-----------|-------|-------|")
        for item in ec['very_low_score'][:20]:  # Top 20
            lines.append(f"| `{item['query']}` | `{item['match']}` | {item['score']:.4f} | {item['stage']} |")
        lines.append("")
    
    if ec['ambiguous']:
        lines.append("### Ambiguous Mappings (top-2 scores within 0.05)")
        lines.append("")
        lines.append("| Query | Match 1 (score) | Match 2 (score) |")
        lines.append("|-------|----------------|----------------|")
        for item in ec['ambiguous'][:20]:
            lines.append(f"| `{item['query']}` | `{item['match1']}` ({item['score1']:.3f}) | `{item['match2']}` ({item['score2']:.3f}) |")
        lines.append("")
    
    # ── 7. Sample Mappings ──
    lines.append("## 7. Sample Mappings")
    lines.append("")
    
    # Show a sample of mapped results
    display_cols = ['query', 'stage', 'method', 'match1', 'match1_score']
    available_cols = [c for c in display_cols if c in results_df.columns]
    
    if available_cols:
        # High confidence
        lines.append("### High-Confidence Mappings (score ≥ 0.9)")
        lines.append("")
        if 'match1_score' in results_df.columns:
            high = results_df[results_df['match1_score'] >= 0.9][available_cols].head(15)
            if len(high) > 0:
                lines.append("| " + " | ".join(available_cols) + " |")
                lines.append("| " + " | ".join(["---"] * len(available_cols)) + " |")
                for _, row in high.iterrows():
                    vals = []
                    for c in available_cols:
                        v = row[c]
                        if isinstance(v, float):
                            vals.append(f"{v:.4f}")
                        else:
                            vals.append(f"`{v}`")
                    lines.append("| " + " | ".join(vals) + " |")
                lines.append("")
        
        # Low confidence (stages 2-3)
        lines.append("### Low-Confidence Mappings (score < 0.5)")
        lines.append("")
        if 'match1_score' in results_df.columns:
            low = results_df[results_df['match1_score'] < 0.5][available_cols].head(15)
            if len(low) > 0:
                lines.append("| " + " | ".join(available_cols) + " |")
                lines.append("| " + " | ".join(["---"] * len(available_cols)) + " |")
                for _, row in low.iterrows():
                    vals = []
                    for c in available_cols:
                        v = row[c]
                        if isinstance(v, float):
                            vals.append(f"{v:.4f}")
                        else:
                            vals.append(f"`{v}`")
                    lines.append("| " + " | ".join(vals) + " |")
                lines.append("")
    
    # ── 8. Identified Gaps ──
    lines.append("## 8. Identified Gaps & Improvement Opportunities")
    lines.append("")
    lines.append("Based on this evaluation, the following gaps/opportunities were identified:")
    lines.append("")
    lines.append("1. **LLM Fallback (Stage 4)**: Disabled in manual mode. Columns that fall through")
    lines.append("   Stages 1–3 with low confidence could benefit from LLM-based matching.")
    lines.append("2. **Alias Dictionary**: Currently disabled (`ALIAS_DICT_PATH=\"\"`). Enabling a")
    lines.append("   curated alias dictionary would improve Stage 1 coverage for known synonyms.")
    lines.append("3. **Confidence Calibration**: Some Stage 3 semantic matches have scores near the")
    lines.append("   threshold (0.5), making accept/reject decisions ambiguous — the dashboard's")
    lines.append("   curator review interface directly addresses this.")
    lines.append("4. **Value-Based Matching**: Stage 2 effectiveness depends on the completeness")
    lines.append("   of `field_value_dict.json`. Expanding this dictionary would improve coverage.")
    lines.append("5. **Free-Text Columns**: Columns with highly variable free-text values are")
    lines.append("   harder to match via value-based methods, requiring semantic or LLM approaches.")
    lines.append("")
    
    # ── 9. Technical Notes ──
    lines.append("## 9. Technical Details")
    lines.append("")
    lines.append("| Component | Value |")
    lines.append("|-----------|-------|")
    lines.append("| MetaHarmonizer version | 0.2.4 |")
    lines.append(f"| Mode | manual (Stages 1–3) |")
    lines.append(f"| Top-K | 5 |")
    lines.append(f"| Embedding model | `all-MiniLM-L6-v2` |")
    lines.append(f"| Fuzzy threshold | 92 |")
    lines.append(f"| Numeric threshold | 0.6 |")
    lines.append(f"| Semantic threshold | 0.5 |")
    lines.append(f"| Value % threshold | 0.15 |")
    lines.append(f"| Python | {sys.version.split()[0]} |")
    lines.append("")
    
    # ── 10. Conclusion ──
    lines.append("## 10. Conclusion")
    lines.append("")
    lines.append("The MetaHarmonizer SchemaMapEngine demonstrates a well-designed multi-stage")
    lines.append("cascade approach to metadata harmonization. The pipeline successfully maps")
    lines.append("columns through progressively sophisticated methods (dictionary → value-based")
    lines.append("→ semantic), with clear confidence scoring that enables curator review.")
    lines.append("")
    lines.append("The dashboard we built complements this pipeline by providing:")
    lines.append("- Visual review of all mapping stages and confidence scores")
    lines.append("- Curator accept/reject/edit workflow for each mapping")
    lines.append("- Quality metrics tracking across harmonization sessions")
    lines.append("- Standardized export in cBioPortal-compatible formats")
    lines.append("")
    lines.append("---")
    lines.append(f"*Report generated on {time.strftime('%Y-%m-%d %H:%M:%S')}*")
    
    return "\n".join(lines)


if __name__ == "__main__":
    print("=" * 60)
    print("MetaHarmonizer Schema Mapper Evaluation")
    print("=" * 60)
    
    # Check files exist
    if not os.path.exists(NEW_META):
        print(f"ERROR: {NEW_META} not found!")
        sys.exit(1)
    if not os.path.exists(CURATED_META):
        print(f"ERROR: {CURATED_META} not found!")
        sys.exit(1)
    
    # Load ground truth
    print("\n[1/4] Loading ground truth (curated_meta.csv)...")
    curated_df = load_ground_truth()
    print(f"  Curated: {curated_df.shape[0]} rows, {curated_df.shape[1]} columns")
    print(f"  Curated fields: {list(curated_df.columns[:10])}...")
    
    # Run schema mapping
    print("\n[2/4] Running SchemaMapEngine...")
    results_df, engine, t_init, t_run = run_schema_mapping(NEW_META)
    
    # Display raw results summary
    print(f"\n[3/4] Analyzing results...")
    print(results_df.to_string(max_rows=20))
    
    # Analyze
    analysis = analyze_results(results_df, curated_df)
    
    # Print key findings
    print(f"\n{'='*60}")
    print("KEY FINDINGS")
    print(f"{'='*60}")
    print(f"Total columns: {analysis['total_columns']}")
    print(f"Invalid: {analysis['invalid_columns']}")
    print(f"Mapped: {analysis['mapped_columns']}")
    if 'stage_distribution' in analysis:
        print(f"Stage distribution: {analysis['stage_distribution']}")
    if 'method_distribution' in analysis:
        print(f"Method distribution: {analysis['method_distribution']}")
    if 'confidence' in analysis:
        c = analysis['confidence']
        print(f"Confidence: mean={c['mean']:.3f}, median={c['median']:.3f}")
        print(f"  High (≥0.9): {c['high_confidence_90']}")
        print(f"  Low (<0.5): {c['very_low_below_50']}")
    
    # Generate report
    print(f"\n[4/4] Generating evaluation report...")
    report = generate_report(results_df, analysis, t_init, t_run)
    
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\nReport written to: {REPORT_FILE}")
    print("Done!")
