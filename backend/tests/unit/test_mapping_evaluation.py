"""Unit tests for the mapping-accuracy evaluator (pure, no DB)."""

from __future__ import annotations

from app.services.mapping_evaluation import evaluate_accuracy


def test_empty_mappings_returns_error():
    assert "error" in evaluate_accuracy("s1", [], {"a": "age"})


def test_precision_recall_f1():
    mappings = [
        {"raw_column": "AGE", "matched_field": "age", "confidence_score": 0.9},   # TP
        {"raw_column": "SEX", "matched_field": "gender", "confidence_score": 0.8},  # FP (wrong)
        {"raw_column": "DOB", "matched_field": "", "confidence_score": 0.0},        # FN
        {"raw_column": "NOTE", "matched_field": "notes", "confidence_score": 0.5},  # FP (no truth)
        {"raw_column": "EXTRA", "matched_field": "", "confidence_score": 0.0},      # TN
    ]
    ground_truth = {
        "AGE": "age",
        "SEX": "sex",
        "DOB": "birth_date",
        "NOTE": "",
        "EXTRA": "",
    }
    res = evaluate_accuracy("s1", mappings, ground_truth)

    assert (res["tp"], res["fp"], res["fn"], res["tn"]) == (1, 2, 1, 1)
    assert res["precision"] == round(1 / 3, 4)
    assert res["recall"] == round(1 / 2, 4)
    assert res["evaluated_columns"] == 5


def test_curator_field_overrides_matched_field():
    mappings = [
        {"raw_column": "AGE", "matched_field": "wrong", "curator_field": "age",
         "confidence_score": 0.9},
    ]
    res = evaluate_accuracy("s1", mappings, {"AGE": "age"})
    assert res["tp"] == 1 and res["fp"] == 0
