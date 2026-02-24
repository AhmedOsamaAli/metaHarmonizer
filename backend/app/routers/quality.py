"""
MetaHarmonizer — Quality / Analytics Router

Provides quality metrics, confidence distributions, and stage breakdowns.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import database as db
from app.models import QualityMetrics
from app.services.analytics import compute_quality_metrics

router = APIRouter(prefix="/api/v1/quality", tags=["quality"])


@router.get("/{study_id}", response_model=QualityMetrics)
async def get_quality_metrics(study_id: str):
    """Returns confidence distribution, stage breakdown, coverage stats."""
    study = db.get_study(study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    return compute_quality_metrics(study_id)
