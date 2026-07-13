"""
Audit repository — read access to the append-only audit log (U11).

Cursor pagination orders by (id DESC) — id is monotonic, so the cursor is just
the last seen id. Filters by study/action/actor are optional and composable.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEvent


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _to_dict(a: AuditEvent) -> dict:
    """Shape an event like the legacy SQLite ``audit_log`` row: the curator
    string lives in ``details['curator']`` and the time in ``created_at``, but
    the dict exposes the legacy ``curator`` / ``timestamp`` keys."""
    curator = a.details.get("curator") if isinstance(a.details, dict) else None
    return {
        "id": a.id,
        "study_id": a.study_id,
        "action": a.action,
        "mapping_id": a.mapping_id,
        "old_value": a.old_value,
        "new_value": a.new_value,
        "curator": curator,
        "timestamp": _iso(a.created_at),
    }


async def add_audit_entry(
    db: AsyncSession,
    study_id: str,
    action: str,
    mapping_id: int | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    actor_id: int | None = None,
    curator: str | None = None,
    details: dict | None = None,
) -> None:
    """Record one decision. ``actor_id`` is the authoritative "who" (the user's
    id, used by admin oversight); ``curator`` is an optional display label kept
    in ``details`` for human-readable rows. ``details`` may carry extra
    structured provenance (e.g. the engine bundle that produced a study)."""
    merged: dict | None = dict(details) if details else None
    if curator:
        merged = {**(merged or {}), "curator": curator}
    db.add(
        AuditEvent(
            study_id=study_id,
            action=action,
            actor_id=actor_id,
            mapping_id=mapping_id,
            old_value=old_value,
            new_value=new_value,
            details=merged,
        )
    )
    await db.flush()


async def get_audit_log(db: AsyncSession, study_id: str) -> list[dict]:
    """All events for one study, newest-first, shaped like the legacy rows."""
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.study_id == study_id)
        .order_by(AuditEvent.created_at.desc())
    )
    return [_to_dict(a) for a in await db.scalars(stmt)]


async def list_audit_events(
    db: AsyncSession,
    *,
    study_id: str | None = None,
    action: str | None = None,
    actor_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    before_id: int | None = None,
    limit: int = 50,
) -> list[AuditEvent]:
    """Return up to ``limit + 1`` events newest-first (the extra row signals a
    next page to the pagination helper)."""
    stmt = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit + 1)

    if study_id is not None:
        stmt = stmt.where(AuditEvent.study_id == study_id)
    if action is not None:
        stmt = stmt.where(AuditEvent.action == action)
    if actor_id is not None:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    if since is not None:
        stmt = stmt.where(AuditEvent.created_at >= since)
    if until is not None:
        stmt = stmt.where(AuditEvent.created_at <= until)
    if before_id is not None:
        stmt = stmt.where(AuditEvent.id < before_id)

    result = await db.execute(stmt)
    return list(result.scalars().all())
