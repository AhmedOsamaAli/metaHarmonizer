"""Mappings router: curator accept/reject/edit + batch, on-demand Stage-4 LLM
rematch, and field suggestions."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import actor_label as _actor_label, require_role
from app.db.models import User
from app.db.session import get_db
from app.models import (
    BatchUpdateRequest,
    BatchUpdateResponse,
    MappingEditRequest,
    MappingOut,
)
from app.repositories import audit as audit_repo
from app.repositories import learned_decisions as ld_repo
from app.repositories import mappings as mappings_repo
from app.repositories import studies as studies_repo
from app.services import active_learning

router = APIRouter(prefix="/api/v1/mappings", tags=["mappings"])


@router.get("/{study_id}", response_model=list[MappingOut])
async def get_study_mappings(study_id: str, db: AsyncSession = Depends(get_db)):
    """Get all mappings for a study."""
    study = await studies_repo.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    mappings = await mappings_repo.get_mappings(db, study_id)
    return mappings


@router.get("/{study_id}/review-queue")
async def get_review_queue(study_id: str, db: AsyncSession = Depends(get_db)):
    """Active-learning review queue (G7): pending mappings ordered risky-first
    and grouped by suggested target so look-alikes are adjacent and batchable.

    Returns ``{ items, stats }``. ``items`` are pending mappings each annotated
    with ``group_key`` / ``group_size`` / ``group_min_confidence``; ``stats``
    summarizes the queue shape (pending, groups, batchable_groups, risky).
    Ordering only — no mapping is changed or hidden.
    """
    study = await studies_repo.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    mappings = await mappings_repo.get_mappings(db, study_id)
    queue = active_learning.build_review_queue(mappings)
    return {"items": queue, "stats": active_learning.queue_stats(queue)}


@router.post("/{mapping_id}/accept", response_model=MappingOut)
async def accept_mapping(
    mapping_id: int,
    remember: bool = Query(False, description="Remember this decision for the curator's future studies (ADR-0002)."),
    user: User = Depends(require_role("curator")),
    db: AsyncSession = Depends(get_db),
):
    """Accept an automated mapping."""
    mapping = await mappings_repo.get_mapping(db, mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    old_status = mapping["status"]
    result = await mappings_repo.update_mapping_status(
        db, mapping_id, "accepted", reviewed_by=user.id
    )

    await audit_repo.add_audit_entry(
        db,
        study_id=mapping["study_id"],
        action="accept",
        mapping_id=mapping_id,
        old_value=old_status,
        new_value="accepted",
        actor_id=user.id,
        curator=_actor_label(user),
    )
    if remember and mapping.get("raw_column"):
        await ld_repo.record_personal(
            db, owner_id=user.id, kind="schema",
            source_key=ld_repo.schema_key(mapping["raw_column"]),
            decision="accept", target_field=mapping.get("matched_field"),
            origin_study_id=mapping["study_id"],
        )
    await db.commit()
    return result


@router.post("/{mapping_id}/reject", response_model=MappingOut)
async def reject_mapping(
    mapping_id: int,
    user: User = Depends(require_role("curator")),
    db: AsyncSession = Depends(get_db),
):
    """Reject an automated mapping."""
    mapping = await mappings_repo.get_mapping(db, mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    old_status = mapping["status"]
    result = await mappings_repo.update_mapping_status(
        db, mapping_id, "rejected", reviewed_by=user.id
    )

    await audit_repo.add_audit_entry(
        db,
        study_id=mapping["study_id"],
        action="reject",
        mapping_id=mapping_id,
        old_value=old_status,
        new_value="rejected",
        actor_id=user.id,
        curator=_actor_label(user),
    )
    await db.commit()
    return result


@router.post("/{mapping_id}/edit", response_model=MappingOut)
async def edit_mapping(
    mapping_id: int,
    body: MappingEditRequest,
    remember: bool = Query(False, description="Remember this decision for the curator's future studies (ADR-0002)."),
    user: User = Depends(require_role("curator")),
    db: AsyncSession = Depends(get_db),
):
    """Curator manually edits a mapping to a different field."""
    mapping = await mappings_repo.get_mapping(db, mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    old_field = mapping.get("matched_field")
    result = await mappings_repo.update_mapping_status(
        db,
        mapping_id,
        status="accepted",
        curator_field=body.new_field,
        curator_note=body.note,
        reviewed_by=user.id,
    )

    await audit_repo.add_audit_entry(
        db,
        study_id=mapping["study_id"],
        action="edit",
        mapping_id=mapping_id,
        old_value=old_field,
        new_value=body.new_field,
        actor_id=user.id,
        curator=_actor_label(user),
    )
    if remember and mapping.get("raw_column"):
        await ld_repo.record_personal(
            db, owner_id=user.id, kind="schema",
            source_key=ld_repo.schema_key(mapping["raw_column"]),
            decision="accept", target_field=body.new_field,
            origin_study_id=mapping["study_id"],
        )
    await db.commit()
    return result


@router.post("/batch", response_model=BatchUpdateResponse)
async def batch_update_mappings(
    body: BatchUpdateRequest,
    user: User = Depends(require_role("curator")),
    db: AsyncSession = Depends(get_db),
):
    """Batch accept or reject multiple mappings."""
    if not body.mapping_ids:
        raise HTTPException(status_code=400, detail="No mapping IDs provided")

    updated = await mappings_repo.batch_update_mapping_status(
        db, body.mapping_ids, body.action, reviewed_by=user.id
    )

    # Audit log for batch
    if body.mapping_ids:
        first = await mappings_repo.get_mapping(db, body.mapping_ids[0])
        if first:
            await audit_repo.add_audit_entry(
                db,
                study_id=first["study_id"],
                action=f"batch_{body.action}",
                old_value=f"{len(body.mapping_ids)} mappings",
                new_value=body.action,
                actor_id=user.id,
                curator=_actor_label(user),
            )

    await db.commit()
    return BatchUpdateResponse(updated=updated, action=body.action)


# Stage 4 — on-demand LLM rematch

@router.post("/{mapping_id}/llm")
async def llm_rematch(
    mapping_id: int,
    user: User = Depends(require_role("curator")),
    db: AsyncSession = Depends(get_db),
):
    """Re-run Stage 4 (LLM / Gemini) for one mapping on demand (needs
    GEMINI_API_KEY). Returns suggested matches without accepting them."""
    mapping = await mappings_repo.get_mapping(db, mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    study = await studies_repo.get_study(db, mapping["study_id"])
    if not study or not study.get("file_path"):
        raise HTTPException(status_code=404, detail="Study CSV not found")

    from app.engine_adapter import get_engine
    from app.core.storage import get_storage

    engine = get_engine()
    try:
        with get_storage().local(study["file_path"]) as local_csv:
            suggestions = engine.llm_match(
                csv_path=str(local_csv),
                raw_column=mapping["raw_column"],
            )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    await audit_repo.add_audit_entry(
        db,
        study_id=mapping["study_id"],
        action="llm_rematch",
        mapping_id=mapping_id,
        old_value=mapping.get("matched_field"),
        new_value=suggestions[0]["field"] if suggestions else None,
        actor_id=user.id,
        curator=_actor_label(user),
    )
    await db.commit()

    return {
        "mapping_id": mapping_id,
        "raw_column": mapping["raw_column"],
        "suggestions": suggestions,
    }


# Column context — sample values to help a curator pick the right term

@router.get("/{study_id}/columns/{column}/context")
async def get_column_context(
    study_id: str,
    column: str,
    limit: int = 15,
    user: User = Depends(require_role("curator")),
    db: AsyncSession = Depends(get_db),
):
    """Return sample distinct values (with counts) for one raw column, capped so
    a huge column can't blow up the response — helps a curator disambiguate."""
    import pandas as pd

    study = await studies_repo.get_study(db, study_id)
    if not study or not study.get("file_path"):
        raise HTTPException(status_code=404, detail="Study CSV not found")

    path = study["file_path"]
    sep = "\t" if str(path).lower().endswith((".tsv", ".txt")) else ","
    try:
        # Only the requested column is read into memory.
        series = pd.read_csv(path, sep=sep, usecols=[column], dtype=str)[column]
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Column '{column}' not found")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Failed to read column: {exc}")

    total = int(len(series))
    non_null = series.dropna()
    null_count = total - int(len(non_null))
    counts = non_null.value_counts()
    limit = max(1, min(limit, 100))
    samples = [
        {"value": str(v), "count": int(c)} for v, c in counts.head(limit).items()
    ]

    return {
        "study_id": study_id,
        "column": column,
        "total_rows": total,
        "distinct_values": int(counts.shape[0]),
        "null_count": null_count,
        "samples": samples,
    }


# ---------------------------------------------------------------------------
# Field suggestions — expose low-confidence / unmapped columns with alternatives
# ---------------------------------------------------------------------------

@router.get("/{study_id}/suggestions")
async def get_field_suggestions(
    study_id: str,
    confidence_threshold: float = 0.5,
    db: AsyncSession = Depends(get_db),
):
    """
    Return columns that are unmapped or below the confidence threshold,
    together with the engine's ranked alternative suggestions.

    Use these as curator "work items" — the alternatives come from the
    `alternatives` JSON column written by the schema mapping pipeline.
    """
    study = await studies_repo.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    all_mappings = await mappings_repo.get_mappings(db, study_id)
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
