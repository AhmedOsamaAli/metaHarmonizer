"""Value-level ontology mapping data access (Postgres)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OntologyMapping


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _to_dict(o: OntologyMapping) -> dict:
    return {
        "id": o.id,
        "study_id": o.study_id,
        "field_name": o.field_name,
        "raw_value": o.raw_value,
        "ontology_term": o.ontology_term,
        "ontology_id": o.ontology_id,
        "confidence_score": o.confidence_score,
        "status": o.status,
        "curator_term": o.curator_term,
        "curator_id": o.curator_id,
        "reviewed_at": _iso(o.reviewed_at),
        "reviewed_by": "curator" if o.reviewed_at else None,
    }


async def insert_ontology_mappings(
    db: AsyncSession, study_id: str, onto_list: list[dict]
) -> None:
    for o in onto_list:
        db.add(
            OntologyMapping(
                study_id=study_id,
                field_name=o["field_name"],
                raw_value=o["raw_value"],
                ontology_term=o.get("ontology_term"),
                ontology_id=o.get("ontology_id"),
                confidence_score=o.get("confidence_score"),
                status=o.get("status", "pending"),
            )
        )
    await db.flush()


async def get_ontology_mappings(db: AsyncSession, study_id: str) -> list[dict]:
    stmt = (
        select(OntologyMapping)
        .where(OntologyMapping.study_id == study_id)
        .order_by(OntologyMapping.field_name)
    )
    return [_to_dict(o) for o in await db.scalars(stmt)]


async def update_ontology_mapping(
    db: AsyncSession,
    mapping_id: int,
    status: str,
    curator_term: str | None = None,
    curator_id: str | None = None,
    reviewed_by: int | None = None,
) -> dict | None:
    """Curator override for an ontology value mapping. When the curator assigns
    a term it's a confirmed human decision, so confidence is set to 1.0 (an
    unmatched value's engine score of 0 would otherwise show as "0%" after
    approval and look broken)."""
    o = await db.get(OntologyMapping, mapping_id)
    if not o:
        return None
    o.status = status
    o.reviewed_at = datetime.now(timezone.utc)
    o.reviewed_by = reviewed_by
    if curator_term:
        o.curator_term = curator_term
        o.curator_id = curator_id
        o.confidence_score = 1.0
    await db.flush()
    return _to_dict(o)


async def delete_unreviewed_ontology(
    db: AsyncSession, study_id: str, fields: set[str], values: set[str]
) -> int:
    """Remove ontology rows the curator hasn't reviewed (``reviewed_at`` is NULL)
    for the given fields+values — used when a column's schema field changes.
    Auto-accepted engine rows are unreviewed and thus removed; a curator's own
    accept/edit (which stamps ``reviewed_at``) is left untouched."""
    fields = {f for f in fields if f}
    if not fields or not values:
        return 0
    stmt = delete(OntologyMapping).where(
        OntologyMapping.study_id == study_id,
        OntologyMapping.field_name.in_(fields),
        OntologyMapping.raw_value.in_(values),
        OntologyMapping.reviewed_at.is_(None),
    )
    res = await db.execute(stmt)
    return res.rowcount or 0


async def existing_value_keys(
    db: AsyncSession, study_id: str, fields: set[str], values: set[str]
) -> set[tuple[str, str]]:
    """(field_name, raw_value) pairs already present for a study — so a re-run
    doesn't duplicate rows the curator has already reviewed."""
    fields = {f for f in fields if f}
    if not fields or not values:
        return set()
    stmt = select(OntologyMapping.field_name, OntologyMapping.raw_value).where(
        OntologyMapping.study_id == study_id,
        OntologyMapping.field_name.in_(fields),
        OntologyMapping.raw_value.in_(values),
    )
    rows = await db.execute(stmt)
    return {(f, v) for f, v in rows.all()}
