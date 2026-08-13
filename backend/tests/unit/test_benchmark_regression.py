from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from scripts.check_benchmark_regression import compare_results
from scripts.eval_ontology import build_summary


BACKEND = Path(__file__).resolve().parents[2]
CORPUS = BACKEND / "benchmarks" / "ontology" / "ncit_disease_efo_v1.csv"
POLICY_PATH = BACKEND / "benchmarks" / "ontology" / "ncit_disease_efo_v1.policy.json"
POLICY = json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def result(*, match_rate: float = 1.0, label_hit_rate: float = 0.405) -> dict:
    return {
        "benchmark_sha256": POLICY["benchmark_sha256"],
        "bundle_sha256": "bundle-sha",
        "query_count": 200,
        "match_rate": match_rate,
        "label_hit_rate": label_hit_rate,
    }


def test_regression_gate_passes_within_floor_and_drop_limits():
    report = compare_results(POLICY, result(label_hit_rate=0.31), result(label_hit_rate=0.295))
    assert report["passed"] is True
    assert report["errors"] == []


def test_regression_gate_rejects_absolute_floor_failure():
    report = compare_results(POLICY, result(label_hit_rate=0.31), result(label_hit_rate=0.289))
    assert report["passed"] is False
    assert any("below floor" in error for error in report["errors"])


def test_regression_gate_rejects_excessive_drop():
    report = compare_results(POLICY, result(label_hit_rate=0.35), result(label_hit_rate=0.32))
    assert report["passed"] is False
    assert any("maximum allowed drop" in error for error in report["errors"])


def test_regression_gate_rejects_corpus_or_sample_mismatch():
    after = result()
    after["benchmark_sha256"] = "different-corpus"
    after["query_count"] = 199
    report = compare_results(POLICY, result(), after)
    assert report["passed"] is False
    assert any("different benchmark corpora" in error for error in report["errors"])
    assert any("minimum is 200" in error for error in report["errors"])


def test_frozen_corpus_matches_policy_and_has_unique_queries():
    rows = list(csv.DictReader(CORPUS.open(encoding="utf-8-sig")))
    assert len(rows) == POLICY["minimum_queries"] == 200
    assert len({row["query"] for row in rows}) == 200
    assert hashlib.sha256(CORPUS.read_bytes()).hexdigest() == POLICY["benchmark_sha256"]


def test_summary_contains_reproducibility_metadata(tmp_path: Path, monkeypatch):
    corpus = tmp_path / "benchmark.csv"
    corpus.write_text("query,ref_match\na,b\n", encoding="utf-8")
    monkeypatch.setenv("BENCHMARK_BUNDLE_SHA256", "bundle-123")
    summary = build_summary(
        benchmark=corpus,
        category="disease",
        source="ncit",
        query_count=2,
        predicted_count=2,
        label_hits=1,
        id_hits=0,
        elapsed_seconds=1.23456,
    )
    assert summary["benchmark_id"] == "benchmark"
    assert summary["bundle_sha256"] == "bundle-123"
    assert summary["match_rate"] == 1.0
    assert summary["label_hit_rate"] == 0.5
    assert len(str(summary["benchmark_sha256"])) == 64
