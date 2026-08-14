from __future__ import annotations

import csv
from pathlib import Path

from scripts.report_kb_refresh import build_report, render_markdown


def write_corpus(path: Path, rows: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["label", "obo_id"])
        for term_id, label in rows:
            writer.writerow([label, term_id])


def comparison() -> dict:
    return {
        "passed": True,
        "metrics": {
            "match_rate": {"before": 0.99, "after": 1.0, "passed": True},
            "label_hit_rate": {"before": 0.30, "after": 0.31, "passed": True},
        },
    }


def test_report_counts_added_removed_and_relabeled_terms(tmp_path: Path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    write_corpus(before / "ncit_disease_corpus.csv", [("A:1", "Old"), ("A:2", "Removed")])
    write_corpus(after / "ncit_disease_corpus.csv", [("A:1", "New"), ("A:3", "Added")])

    report = build_report(
        before_dir=before,
        after_dir=after,
        comparison=comparison(),
        before_sha="before",
        after_sha="after",
    )

    corpus = report["corpora"]["ncit_disease_corpus.csv"]
    assert corpus["row_delta"] == 0
    assert corpus["added_ids"] == ["A:3"]
    assert corpus["removed_ids"] == ["A:2"]
    assert corpus["relabeled_terms"] == [{"id": "A:1", "before": "Old", "after": "New"}]
    assert report["removed_term_count"] == 1
    assert report["relabeled_term_count"] == 1


def test_markdown_reports_quality_delta_and_learned_decision_risk(tmp_path: Path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    write_corpus(before / "efo_phenotype_corpus.csv", [("EFO:1", "Term")])
    write_corpus(after / "efo_phenotype_corpus.csv", [("EFO:1", "Term")])
    report = build_report(
        before_dir=before,
        after_dir=after,
        comparison=comparison(),
        before_sha="before",
        after_sha="after",
    )

    markdown = render_markdown(report)
    assert "| match rate | 99.00% | 100.00% | +1.00% | pass |" in markdown
    assert "refresh does not modify learned decisions" in markdown
    assert "removed **0** and relabeled **0** ontology IDs" in markdown