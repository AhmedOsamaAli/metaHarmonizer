"""
MetaHarmonizer — Quality / Analytics Router

Provides quality metrics, confidence distributions, and stage breakdowns.
Also provides a precision/recall evaluation endpoint against ground-truth CSVs.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, HTTPException

from app import database as db
from app.models import QualityMetrics
from app.services.analytics import compute_quality_metrics

router = APIRouter(prefix="/api/v1/quality", tags=["quality"])

# Canonical path to the engine evaluation directory (absolute, resolved at import time)
_BACKEND_DIR = Path(__file__).resolve().parents[2]  # backend/
_EVAL_DIRS = [
    _BACKEND_DIR.parent / "engine" / "data" / "schema_mapping_eval",  # engine/data/schema_mapping_eval/
    _BACKEND_DIR / "data" / "schema_mapping_eval",                     # backend/data/schema_mapping_eval/
]


def _load_eval_csv(csv_path: Path) -> dict[str, str]:
    """
    Parse a schema_mapping_eval CSV into a ground-truth dict.

    Format: query, stage, method, match1, match1_score, ...
    Rows where match1 is empty or stage == 'invalid' are treated as "no mapping".
    """
    ground_truth: dict[str, str] = {}
    try:
        with csv_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                raw_col = (row.get("query") or "").strip()
                match1 = (row.get("match1") or "").strip()
                stage = (row.get("stage") or "").strip().lower()
                if not raw_col:
                    continue
                # Mark as explicitly unmapped if stage is invalid or match1 empty
                if stage == "invalid" or not match1:
                    ground_truth[raw_col] = ""
                else:
                    ground_truth[raw_col] = match1
    except Exception:
        return {}
    return ground_truth


def _find_eval_csv_for_study(study: dict) -> Optional[Path]:
    """
    Look for a *_manual.csv in any eval dir whose stem contains the study file stem.
    The study file_path stem may carry a UUID suffix (e.g. new_meta_b3a3cd58_9a1b2c3d)
    so we also try with the suffix stripped.
    Searches both engine/data/schema_mapping_eval/ and backend/data/schema_mapping_eval/.
    """
    file_path = study.get("file_path") or ""
    full_stem = Path(file_path).stem  # e.g. "new_meta_b3a3cd58_9a1b2c3d"

    import re as _re
    stems_to_try = [full_stem]
    stripped = _re.sub(r'_[0-9a-f]{8}$', '', full_stem)
    if stripped and stripped != full_stem:
        stems_to_try.append(stripped)

    for eval_dir in _EVAL_DIRS:
        if not eval_dir.is_dir():
            continue
        for p in eval_dir.glob("*_manual.csv"):
            for s in stems_to_try:
                if s in p.stem:
                    return p
    return None


@router.get("/{study_id}", response_model=QualityMetrics)
async def get_quality_metrics(study_id: str):
    """Returns confidence distribution, stage breakdown, coverage stats."""
    study = db.get_study(study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    return compute_quality_metrics(study_id)


@router.post("/{study_id}/evaluate")
async def evaluate_mapping_accuracy(
    study_id: str,
    ground_truth: Optional[dict[str, str]] = Body(
        default=None,
        description=(
            "Optional JSON dict mapping raw_column → correct_curated_field. "
            "If omitted the endpoint auto-detects from schema_mapping_eval/ CSVs."
        ),
        embed=True,
    ),
):
    """
    Compute precision, recall, and F1 for a study's schema mappings.

    **Ground truth source (in priority order):**
    1. `ground_truth` JSON body — caller-supplied dict
    2. Auto-detect matching `*_manual.csv` in `engine/data/schema_mapping_eval/`

    Returns per-column breakdown and aggregate TP/FP/FN/TN / P / R / F1.
    """
    study = db.get_study(study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    # Resolve ground truth
    if ground_truth is None:
        eval_csv = _find_eval_csv_for_study(study)
        if eval_csv is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "No ground_truth provided and no matching *_manual.csv found in "
                    "engine/data/schema_mapping_eval/ or backend/data/schema_mapping_eval/ "
                    "for this study.  Pass a ground_truth dict in the request body."
                ),
            )
        ground_truth = _load_eval_csv(eval_csv)
        source = str(eval_csv.name)
    else:
        source = "caller-provided"

    if not ground_truth:
        raise HTTPException(
            status_code=422,
            detail="ground_truth dict is empty — nothing to evaluate."
        )

    result = db.compute_mapping_accuracy(study_id, ground_truth)
    result["ground_truth_source"] = source
    return result
