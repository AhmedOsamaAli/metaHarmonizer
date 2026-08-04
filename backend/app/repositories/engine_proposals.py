from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EngineProposal


async def lookup(
    db: AsyncSession, *, scope_key: str, kind: str, keys: list[str]
) -> dict[str, dict]:
    if not keys:
        return {}
    rows = list(
        await db.scalars(
            select(EngineProposal).where(
                EngineProposal.scope_key == scope_key,
                EngineProposal.kind == kind,
                EngineProposal.source_key.in_(keys),
            )
        )
    )
    if rows:
        ids = [row.id for row in rows]
        await db.execute(
            update(EngineProposal)
            .where(EngineProposal.id.in_(ids))
            .values(
                use_count=EngineProposal.use_count + 1,
                last_used_at=datetime.now(timezone.utc),
            )
        )
    return {row.source_key: dict(row.payload) for row in rows}


async def upsert_many(
    db: AsyncSession,
    *,
    scope_key: str,
    kind: str,
    proposals: dict[str, dict],
    engine_version: str | None,
) -> None:
    if not proposals:
        return
    stmt = pg_insert(EngineProposal).values(
        [
            {
                "scope_key": scope_key,
                "kind": kind,
                "source_key": key,
                "payload": payload,
                "engine_version": engine_version,
            }
            for key, payload in proposals.items()
        ]
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_engine_proposal_scope_key",
        set_={
            "payload": stmt.excluded.payload,
            "engine_version": stmt.excluded.engine_version,
            "updated_at": func.now(),
            "last_used_at": func.now(),
        },
    )
    await db.execute(stmt)