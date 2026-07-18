"""Ontology-snapshot data access (reproducibility pin; engine contract F-11).

The ontology knowledge base (FAISS index + concept tables + biomedical
encoders) is global to a deployment and pinned to one bundle at a time. A
snapshot is a small record of *which engine + KB bundle was in effect*, so
every study's ontology mappings are traceable and reproducible. Exactly one
snapshot is ``current``; new studies are stamped with it. When the KB bundle or
engine version changes (a deliberate refresh), the current snapshot is bumped.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OntologySnapshot


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _to_dict(s: OntologySnapshot) -> dict:
    return {
        "id": s.id,
        "label": s.label,
        "is_current": s.is_current,
        "engine_version": s.engine_version,
        "source": s.source,
        "created_at": _iso(s.created_at),
    }


async def get_current(db: AsyncSession) -> OntologySnapshot | None:
    return (
        await db.execute(
            select(OntologySnapshot).where(OntologySnapshot.is_current.is_(True))
        )
    ).scalar_one_or_none()


async def get_by_label(db: AsyncSession, label: str) -> OntologySnapshot | None:
    return (
        await db.execute(select(OntologySnapshot).where(OntologySnapshot.label == label))
    ).scalar_one_or_none()


async def list_snapshots(db: AsyncSession) -> list[dict]:
    rows = (
        await db.execute(
            select(OntologySnapshot).order_by(
                OntologySnapshot.is_current.desc(), OntologySnapshot.created_at.desc()
            )
        )
    ).scalars().all()
    return [_to_dict(s) for s in rows]


async def _set_current(db: AsyncSession, snapshot_id: int) -> None:
    # Only one snapshot is current (the KB is global to the deployment).
    await db.execute(update(OntologySnapshot).values(is_current=False))
    await db.execute(
        update(OntologySnapshot).where(OntologySnapshot.id == snapshot_id).values(is_current=True)
    )


def _make_label(engine_version: str | None, source: str | None) -> str:
    """Deterministic, human-readable id for an (engine, KB-bundle) identity —
    e.g. ``0.4.0+48aca2977022``. Deterministic so the same identity maps to the
    same row (the label is unique)."""
    ev = engine_version or "unknown"
    src = (source or "local")[:12]
    return f"{ev}+{src}"


async def ensure_current(
    db: AsyncSession, *, engine_version: str | None, source: str | None
) -> OntologySnapshot:
    """Ensure a *current* snapshot exists for the given engine + KB identity.

    Idempotent: if the current snapshot already matches, it's returned
    unchanged. If the identity changed (KB refresh or engine bump), a new
    snapshot is created — or an existing one with the same label is re-promoted
    — and marked current. Callers commit.
    """
    current = await get_current(db)
    if (
        current is not None
        and current.engine_version == engine_version
        and current.source == source
    ):
        return current

    label = _make_label(engine_version, source)
    existing = await get_by_label(db, label)
    if existing is not None:
        await _set_current(db, existing.id)
        return existing

    snap = OntologySnapshot(
        label=label,
        engine_version=engine_version,
        source=source,
        is_current=False,
    )
    db.add(snap)
    await db.flush()
    await _set_current(db, snap.id)
    return snap
