"""Mapping-accuracy evaluation (precision/recall/F1 vs a ground-truth dict).

Pure business logic over already-loaded mapping rows — no database access, so it
is trivially unit-testable and lives outside the repository layer.
"""

from __future__ import annotations

from typing import Any


def evaluate_accuracy(
    study_id: str, mappings: list[dict[str, Any]], ground_truth: dict[str, str]
) -> dict[str, Any]:
    """Score ``mappings`` against a ``raw_column -> correct_field`` dict.

    Empty/None ground-truth values mean "no correct mapping exists".
    """
    if not mappings:
        return {"error": "No mappings found for this study"}

    tp = fp = fn = tn = 0
    per_column: list[dict[str, Any]] = []

    for m in mappings:
        col = m["raw_column"]
        if col not in ground_truth:
            continue

        correct = (ground_truth[col] or "").strip().lower()
        predicted = (m.get("curator_field") or m.get("matched_field") or "").strip().lower()
        score = m.get("confidence_score", 0)

        if correct and predicted:
            result = "TP" if predicted == correct else "FP"
            tp += result == "TP"
            fp += result == "FP"
            per_column.append(
                {"column": col, "result": result, "predicted": predicted,
                 "correct": correct, "score": score}
            )
        elif correct and not predicted:
            fn += 1
            per_column.append(
                {"column": col, "result": "FN", "predicted": None,
                 "correct": correct, "score": 0}
            )
        elif not correct and predicted:
            fp += 1
            per_column.append(
                {"column": col, "result": "FP", "predicted": predicted,
                 "correct": "(none)", "score": score}
            )
        else:  # not correct and not predicted
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "study_id": study_id,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "evaluated_columns": len(per_column) + tn,
        "per_column": per_column,
    }
