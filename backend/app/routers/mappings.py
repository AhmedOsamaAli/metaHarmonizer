"""
MetaHarmonizer — Mappings Router

Curator review endpoints: accept, reject, edit, batch update individual mappings.
"""

from __future__ import annotations

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
