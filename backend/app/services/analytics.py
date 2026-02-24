"""
MetaHarmonizer Dashboard — Analytics Service

Computes quality metrics, confidence distributions, and stage breakdowns
from mapping data stored in the database.
"""

from __future__ import annotations

from app import database as db
from app.models import (
    ConfidenceBucket,
    QualityMetrics,
    StageBreakdown,
)


def compute_quality_metrics(study_id: str) -> QualityMetrics:
    """Build a complete quality report for a given study."""
    mappings = db.get_mappings(study_id)
    study = db.get_study(study_id)

    total = len(mappings)
    if total == 0:
        return QualityMetrics(
            study_id=study_id,
            total_columns=0,
            mapped_columns=0,
            unmapped_columns=0,
            avg_confidence=0.0,
            auto_accepted=0,
            pending_review=0,
            rejected=0,
            new_field_suggestions=0,
            stage_breakdown=[],
            confidence_distribution=[],
        )

    mapped = [m for m in mappings if m["matched_field"] is not None]
    unmapped = total - len(mapped)

    scores = [m["confidence_score"] for m in mappings if m["confidence_score"] is not None]
    avg_conf = sum(scores) / len(scores) if scores else 0.0

    accepted = sum(1 for m in mappings if m["status"] == "accepted")
    pending = sum(1 for m in mappings if m["status"] == "pending")
    rejected = sum(1 for m in mappings if m["status"] == "rejected")
    new_fields = sum(
        1 for m in mappings
        if m["matched_field"] is None and m["stage"] == "unmapped"
    )

    # Stage breakdown
    stage_counts: dict[str, int] = {}
    for m in mappings:
        stage = m.get("stage", "unmapped") or "unmapped"
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

    stage_breakdown = [
        StageBreakdown(
            stage=stage,
            count=count,
            percentage=round(count / total * 100, 1),
        )
        for stage, count in sorted(stage_counts.items())
    ]

    # Confidence buckets
    buckets_def = [
        ("0.0-0.2", 0.0, 0.2),
        ("0.2-0.4", 0.2, 0.4),
        ("0.4-0.6", 0.4, 0.6),
        ("0.6-0.8", 0.6, 0.8),
        ("0.8-1.0", 0.8, 1.01),
    ]
    confidence_distribution = []
    for label, lo, hi in buckets_def:
        cnt = sum(1 for s in scores if lo <= s < hi)
        confidence_distribution.append(
            ConfidenceBucket(bucket=label, min_val=lo, max_val=hi, count=cnt)
        )

    return QualityMetrics(
        study_id=study_id,
        total_columns=total,
        mapped_columns=len(mapped),
        unmapped_columns=unmapped,
        avg_confidence=round(avg_conf, 3),
        auto_accepted=accepted,
        pending_review=pending,
        rejected=rejected,
        new_field_suggestions=new_fields,
        stage_breakdown=stage_breakdown,
        confidence_distribution=confidence_distribution,
    )
