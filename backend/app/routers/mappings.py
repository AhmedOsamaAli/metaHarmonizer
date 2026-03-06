"""
MetaHarmonizer — Mappings Router

Curator review endpoints: accept, reject, edit, batch update individual mappings.
Also: on-demand Stage 4 LLM re-match and field suggestions.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from app import database as db
from app.models import (
    BatchUpdateRequest,
    BatchUpdateResponse,
    MappingEditRequest,
    MappingOut,
)

router = APIRouter(prefix="/api/v1/mappings", tags=["mappings"])


@router.get("/{study_id}", response_model=list[MappingOut])
async def get_study_mappings(study_id: str):
    """Get all mappings for a study."""
    study = db.get_study(study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    mappings = db.get_mappings(study_id)
    return mappings


@router.post("/{mapping_id}/accept", response_model=MappingOut)
async def accept_mapping(mapping_id: int):
    """Accept an automated mapping."""
    mapping = db.get_mapping(mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    old_status = mapping["status"]
    result = db.update_mapping_status(mapping_id, "accepted")

    db.add_audit_entry(
        study_id=mapping["study_id"],
        action="accept",
        mapping_id=mapping_id,
        old_value=old_status,
        new_value="accepted",
    )
    return result


@router.post("/{mapping_id}/reject", response_model=MappingOut)
async def reject_mapping(mapping_id: int):
    """Reject an automated mapping."""
    mapping = db.get_mapping(mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    old_status = mapping["status"]
    result = db.update_mapping_status(mapping_id, "rejected")

    db.add_audit_entry(
        study_id=mapping["study_id"],
        action="reject",
        mapping_id=mapping_id,
        old_value=old_status,
        new_value="rejected",
    )
    return result


@router.post("/{mapping_id}/edit", response_model=MappingOut)
async def edit_mapping(mapping_id: int, body: MappingEditRequest):
    """Curator manually edits a mapping to a different field."""
    mapping = db.get_mapping(mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    old_field = mapping.get("matched_field")
    result = db.update_mapping_status(
        mapping_id,
        status="accepted",
        curator_field=body.new_field,
        curator_note=body.note,
    )

    db.add_audit_entry(
        study_id=mapping["study_id"],
        action="edit",
        mapping_id=mapping_id,
        old_value=old_field,
        new_value=body.new_field,
    )
    return result


@router.post("/batch", response_model=BatchUpdateResponse)
async def batch_update_mappings(body: BatchUpdateRequest):
    """Batch accept or reject multiple mappings."""
    if not body.mapping_ids:
        raise HTTPException(status_code=400, detail="No mapping IDs provided")

    updated = db.batch_update_mapping_status(body.mapping_ids, body.action)

    # Audit log for batch
    if body.mapping_ids:
        first = db.get_mapping(body.mapping_ids[0])
        if first:
            db.add_audit_entry(
                study_id=first["study_id"],
                action=f"batch_{body.action}",
                old_value=f"{len(body.mapping_ids)} mappings",
                new_value=body.action,
            )

    return BatchUpdateResponse(updated=updated, action=body.action)


# ---------------------------------------------------------------------------
# Stage 4 — on-demand LLM rematch
# ---------------------------------------------------------------------------

@router.post("/{mapping_id}/llm")
async def llm_rematch(mapping_id: int):
    """
    Re-run Stage 4 (LLM / Gemini) for a single mapping on demand.

    Requires GEMINI_API_KEY to be set in the backend environment.
    Returns a list of suggested field matches without automatically accepting them.
    """
    mapping = db.get_mapping(mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    study = db.get_study(mapping["study_id"])
    if not study or not study.get("file_path"):
        raise HTTPException(status_code=404, detail="Study CSV not found")

    from app.services.harmonizer import run_llm_match_for_column

    try:
        suggestions = run_llm_match_for_column(
            csv_path=study["file_path"],
            raw_column=mapping["raw_column"],
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    db.add_audit_entry(
        study_id=mapping["study_id"],
        action="llm_rematch",
        mapping_id=mapping_id,
        old_value=mapping.get("matched_field"),
        new_value=suggestions[0]["field"] if suggestions else None,
    )

    return {
        "mapping_id": mapping_id,
        "raw_column": mapping["raw_column"],
        "suggestions": suggestions,
    }


# ---------------------------------------------------------------------------
# Field suggestions — expose low-confidence / unmapped columns with alternatives
# ---------------------------------------------------------------------------

@router.get("/{study_id}/suggestions")
async def get_field_suggestions(study_id: str, confidence_threshold: float = 0.5):
    """
    Return columns that are unmapped or below the confidence threshold,
    together with the engine's ranked alternative suggestions.

    Use these as curator "work items" — the alternatives come from the
    `alternatives` JSON column written by the schema mapping pipeline.
    """
    study = db.get_study(study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    all_mappings = db.get_mappings(study_id)
    suggestions = []

    for m in all_mappings:
        # Skip columns that are already curated
        if m.get("status") in ("accepted", "rejected") and m.get("curator_field"):
            continue

        is_unmapped = (m.get("stage") or "").lower() == "unmapped"
        low_confidence = (m.get("confidence_score") or 0.0) < confidence_threshold

        if not (is_unmapped or low_confidence):
            continue

        # Parse stored alternatives JSON
        alts_raw = m.get("alternatives")
        alternatives: list[dict] = []
        if alts_raw:
            try:
                parsed = json.loads(alts_raw) if isinstance(alts_raw, str) else alts_raw
                for item in parsed[:5]:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        alternatives.append({"field": item[0], "confidence": round(float(item[1]), 4)})
                    elif isinstance(item, dict):
                        alternatives.append(item)
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

        suggestions.append({
            "mapping_id": m["id"],
            "raw_column": m["raw_column"],
            "current_match": m.get("matched_field"),
            "current_confidence": m.get("confidence_score"),
            "stage": m.get("stage"),
            "status": m.get("status"),
            "alternatives": alternatives,
        })

    return {"study_id": study_id, "suggestions": suggestions, "count": len(suggestions)}
