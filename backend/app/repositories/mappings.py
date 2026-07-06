"""Column-level mapping data access (Postgres).

Dict rows mirror the legacy SQLite layer: ``alternatives`` is a list,
``reviewed_at`` is an ISO string, and ``reviewed_by`` is synthesized as the
literal ``"curator"`` whenever a row has been reviewed (the legacy column held
that constant; the Postgres FK column stays NULL since no real id is recorded).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Mapping


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _to_dict(m: Mapping) -> dict:
    return {
        "id": m.id,
        "study_id": m.study_id,
        "raw_column": m.raw_column,
        "matched_field": m.matched_field,
        "confidence_score": m.confidence_score,
        "stage": m.stage,
        "method": m.method,
        "alternatives": m.alternatives or [],
        "status": m.status,
        "curator_field": m.curator_field,
        "curator_note": m.curator_note,
        "reviewed_at": _iso(m.reviewed_at),
        "reviewed_by": "curator" if m.reviewed_at else None,
    }


async def insert_mappings(
    db: AsyncSession, study_id: str, mappings_list: list[dict]
) -> None:
    for m in mappings_list:
        db.add(
            Mapping(
                study_id=study_id,
                raw_column=m["raw_column"],
                matched_field=m.get("matched_field"),
                confidence_score=m.get("confidence_score"),
                stage=m.get("stage"),
                method=m.get("method"),
                alternatives=m.get("alternatives", []),
                status=m.get("status", "pending"),
            )
        )
    await db.flush()


async def get_mappings(db: AsyncSession, study_id: str) -> list[dict]:
    stmt = (
        select(Mapping)
        .where(Mapping.study_id == study_id)
        .order_by(Mapping.confidence_score.desc().nullslast())
    )
    return [_to_dict(m) for m in await db.scalars(stmt)]


async def get_mapping(db: AsyncSession, mapping_id: int) -> dict | None:
    m = await db.get(Mapping, mapping_id)
    return _to_dict(m) if m else None


async def update_mapping_status(
    db: AsyncSession,
    mapping_id: int,
    status: str,
    curator_field: str | None = None,
    curator_note: str | None = None,
    reviewed_by: int | None = None,
) -> dict | None:
    m = await db.get(Mapping, mapping_id)
    if not m:
        return None
    m.status = status
    m.curator_field = curator_field
    m.curator_note = curator_note
    m.reviewed_at = datetime.now(timezone.utc)
    m.reviewed_by = reviewed_by
    await db.flush()
    return _to_dict(m)


async def batch_update_mapping_status(
    db: AsyncSession, mapping_ids: list[int], status: str, reviewed_by: int | None = None
) -> int:
    if not mapping_ids:
        return 0
    now = datetime.now(timezone.utc)
    res = await db.execute(
        update(Mapping)
        .where(Mapping.id.in_(mapping_ids))
        .values(status=status, reviewed_at=now, reviewed_by=reviewed_by)
    )
    return res.rowcount or 0
