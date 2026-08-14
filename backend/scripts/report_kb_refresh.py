"""Create machine-readable and Markdown reports for a KB refresh."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


ID_COLUMNS = ("obo_id", "clean_code", "iri", "short_form")
LABEL_COLUMNS = ("label", "official_label")


def load_corpus(path: Path) -> tuple[int, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        id_column = next((column for column in ID_COLUMNS if column in fields), None)
        label_column = next((column for column in LABEL_COLUMNS if column in fields), None)
        if id_column is None or label_column is None:
            raise ValueError(f"Unsupported corpus columns in {path.name}: {fields}")
        rows = list(reader)
    terms = {
        row[id_column].strip(): row[label_column].strip()
        for row in rows
        if row.get(id_column, "").strip()
    }
    return len(rows), terms


def compare_corpora(before_dir: Path, after_dir: Path) -> dict[str, dict[str, Any]]:
    names = sorted(
        {path.name for path in before_dir.glob("*_corpus.csv")}
        | {path.name for path in after_dir.glob("*_corpus.csv")}
    )
    result: dict[str, dict[str, Any]] = {}
    for name in names:
        before_path = before_dir / name
        after_path = after_dir / name
        before_rows, before_terms = load_corpus(before_path) if before_path.exists() else (0, {})
        after_rows, after_terms = load_corpus(after_path) if after_path.exists() else (0, {})
        added = sorted(after_terms.keys() - before_terms.keys())
        removed = sorted(before_terms.keys() - after_terms.keys())
        relabeled = [
            {
                "id": term_id,
                "before": before_terms[term_id],
                "after": after_terms[term_id],
            }
            for term_id in sorted(before_terms.keys() & after_terms.keys())
            if before_terms[term_id] != after_terms[term_id]
        ]
        result[name] = {
            "before_rows": before_rows,
            "after_rows": after_rows,
            "row_delta": after_rows - before_rows,
            "before_unique_terms": len(before_terms),
            "after_unique_terms": len(after_terms),
            "added_count": len(added),
            "removed_count": len(removed),
            "relabeled_count": len(relabeled),
            "added_ids": added,
            "removed_ids": removed,
            "relabeled_terms": relabeled,
        }
    return result


def build_report(
    *,
    before_dir: Path,
    after_dir: Path,
    comparison: dict[str, Any],
    before_sha: str,
    after_sha: str,
) -> dict[str, Any]:
    corpora = compare_corpora(before_dir, after_dir)
    return {
        "schema_version": 1,
        "before_bundle_sha256": before_sha,
        "after_bundle_sha256": after_sha,
        "passed": bool(comparison.get("passed")),
        "corpora": corpora,
        "quality_metrics": comparison.get("metrics", {}),
        "removed_term_count": sum(item["removed_count"] for item in corpora.values()),
        "relabeled_term_count": sum(item["relabeled_count"] for item in corpora.values()),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "### KB refresh impact",
        "",
        f"- Previous bundle: `{report['before_bundle_sha256']}`",
        f"- Candidate bundle: `{report['after_bundle_sha256']}`",
        f"- Accuracy gate: **{'passed' if report['passed'] else 'failed'}**",
        "",
        "| Corpus | Rows before | Rows after | Delta | Added IDs | Removed IDs | Relabeled IDs |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, corpus in report["corpora"].items():
        lines.append(
            f"| {name.removesuffix('_corpus.csv')} | {corpus['before_rows']:,} | "
            f"{corpus['after_rows']:,} | {corpus['row_delta']:+,} | "
            f"{corpus['added_count']:,} | {corpus['removed_count']:,} | "
            f"{corpus['relabeled_count']:,} |"
        )
    lines.extend([
        "",
        "| Quality metric | Before | After | Delta | Result |",
        "|---|---:|---:|---:|---|",
    ])
    for name, metric in report["quality_metrics"].items():
        before = float(metric["before"])
        after = float(metric["after"])
        lines.append(
            f"| {name.replace('_', ' ')} | {before:.2%} | {after:.2%} | "
            f"{after - before:+.2%} | {'pass' if metric['passed'] else 'fail'} |"
        )
    removed = report["removed_term_count"]
    relabeled = report["relabeled_term_count"]
    lines.extend([
        "",
        "#### Learned-decision compatibility",
        "",
        "The refresh does not modify learned decisions; they remain in PostgreSQL. "
        f"This candidate removed **{removed:,}** and relabeled **{relabeled:,}** ontology IDs. "
        + (
            "Review the affected IDs in `kb-refresh-impact.json`: removed targets may be stale, "
            "while relabeled targets may retain an older display label."
            if removed or relabeled
            else "No learned ontology target is at risk from an ID removal or relabel in this refresh."
        ),
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report KB refresh impact.")
    parser.add_argument("--before-dir", type=Path, required=True)
    parser.add_argument("--after-dir", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--before-sha", required=True)
    parser.add_argument("--after-sha", required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args(argv)

    report = build_report(
        before_dir=args.before_dir,
        after_dir=args.after_dir,
        comparison=json.loads(args.comparison.read_text(encoding="utf-8")),
        before_sha=args.before_sha,
        after_sha=args.after_sha,
    )
    args.output_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.output_markdown.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())