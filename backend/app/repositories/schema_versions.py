"""Schema-version data access (U9).

Each engine target schema (gdc / cbioportal / cmd / …) has its own version
lineage. A version is a named, immutable snapshot of that target's
target-attributes CSV; exactly one version per target is *current*. New studies
are stamped with the current version for reproducibility; existing studies stay
pinned to whatever they were harmonized against.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SchemaVersion


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _to_dict(s: SchemaVersion) -> dict:
    return {
        "id": s.id,
        "target_schema": s.target_schema,
        "label": s.label,
        "is_current": s.is_current,
        "source_path": s.source_path,
        "created_at": _iso(s.created_at),
    }


async def list_versions(
    db: AsyncSession, target_schema: str | None = None
) -> list[dict]:
    stmt = select(SchemaVersion)
    if target_schema:
        stmt = stmt.where(SchemaVersion.target_schema == target_schema)
    stmt = stmt.order_by(
        SchemaVersion.target_schema.asc(), SchemaVersion.created_at.desc()
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_dict(s) for s in rows]


async def get_current(db: AsyncSession, target_schema: str) -> SchemaVersion | None:
    return (
        await db.execute(
            select(SchemaVersion).where(
                SchemaVersion.target_schema == target_schema,
                SchemaVersion.is_current.is_(True),
            )
        )
    ).scalar_one_or_none()


async def get_by_id(db: AsyncSession, version_id: int) -> SchemaVersion | None:
    return await db.get(SchemaVersion, version_id)


async def get_by_label(
    db: AsyncSession, target_schema: str, label: str
) -> SchemaVersion | None:
    return (
        await db.execute(
            select(SchemaVersion).where(
                SchemaVersion.target_schema == target_schema,
                SchemaVersion.label == label,
            )
        )
    ).scalar_one_or_none()


async def create_version(
    db: AsyncSession,
    *,
    label: str,
    source_path: str,
    target_schema: str,
    make_current: bool = False,
) -> SchemaVersion:
    version = SchemaVersion(
        target_schema=target_schema,
        label=label,
        source_path=source_path,
        is_current=False,
    )
    db.add(version)
    await db.flush()
    if make_current:
        await _set_current(db, version.id, target_schema)
    return version


async def _set_current(db: AsyncSession, version_id: int, target_schema: str) -> None:
    # Clear + set within this target only, so each target keeps its own current.
    await db.execute(
        update(SchemaVersion)
        .where(SchemaVersion.target_schema == target_schema)
        .values(is_current=False)
    )
    await db.execute(
        update(SchemaVersion)
        .where(SchemaVersion.id == version_id)
        .values(is_current=True)
    )


async def promote(db: AsyncSession, version_id: int) -> SchemaVersion | None:
    version = await db.get(SchemaVersion, version_id)
    if not version:
        return None
    await _set_current(db, version_id, version.target_schema)
    return version


async def ensure_seed_versions(db: AsyncSession, targets: dict[str, str]) -> None:
    """Seed a ``v1`` current version for each installed target schema.

    ``targets`` maps a target-schema key (gdc / cbioportal / …) to the path of
    its target-attributes CSV. Idempotent: a target that already has any version
    is skipped. New studies are stamped with the current version so they can be
    reproduced against the exact target schema they were harmonized with.
    """
    for target_schema, source_path in targets.items():
        existing = (
            await db.execute(
                select(SchemaVersion.id)
                .where(SchemaVersion.target_schema == target_schema)
                .limit(1)
            )
        ).first()
        if existing:
            continue
        await create_version(
            db,
            label="v1",
            source_path=source_path,
            target_schema=target_schema,
            make_current=True,
        )
    await db.commit()
