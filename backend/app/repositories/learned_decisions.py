"""Two-layer curation KB data access (ADR-0002).

Remembered curator decisions reused across studies. A ``personal`` layer is
owned by each curator; an admin-promoted ``shared`` layer applies to everyone.
Lookup precedence is personal → shared (a curator's own row overrides the team
baseline for that curator only).

Only this module (plus the services/routers that call it) touches the
``learned_decisions`` table.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LearnedDecision

# Normalization shared by the writer and the reader so keys match across studies:
# lowercase, trim, and collapse any run of whitespace/punctuation/underscore to a
# single space (so "Body_Site", "body-site", "  body   site " all agree).
_COLLAPSE = re.compile(r"[\s\W_]+")


def normalize(value: str | None) -> str:
    if not value:
        return ""
    return _COLLAPSE.sub(" ", value.strip().lower()).strip()


def schema_key(raw_column: str) -> str:
    """Lookup key for a schema (column-name) decision."""
    return normalize(raw_column)


def ontology_key(field_name: str, raw_value: str) -> str:
    """Lookup key for an ontology (value) decision: ``field::value`` normalized."""
    return f"{normalize(field_name)}::{normalize(raw_value)}"


async def record_personal(
    db: AsyncSession,
    *,
    owner_id: int,
    kind: str,
    source_key: str,
    decision: str,
    target_field: str | None = None,
    target_term: str | None = None,
    target_id: str | None = None,
    origin_study_id: str | None = None,
) -> None:
    """Upsert a curator's personal decision, bumping ``support_count`` on repeat.

    Conflicts resolve on the partial unique index over
    ``(owner_id, kind, source_key) WHERE scope='personal'``.
    """
    stmt = pg_insert(LearnedDecision).values(
        scope="personal",
        owner_id=owner_id,
        kind=kind,
        source_key=source_key,
        decision=decision,
        target_field=target_field,
        target_term=target_term,
        target_id=target_id,
        origin_study_id=origin_study_id,
        support_count=1,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["owner_id", "kind", "source_key"],
        index_where=text("scope = 'personal'"),
        set_={
            "decision": stmt.excluded.decision,
            "target_field": stmt.excluded.target_field,
            "target_term": stmt.excluded.target_term,
            "target_id": stmt.excluded.target_id,
            "support_count": LearnedDecision.support_count + 1,
            "updated_at": func.now(),
        },
    )
    await db.execute(stmt)


async def lookup_batch(
    db: AsyncSession,
    *,
    kind: str,
    keys: list[str],
    owner_id: int | None,
) -> dict[str, dict[str, Any]]:
    """Resolve many keys at once. Returns ``{source_key: decision-dict}``.

    Personal rows (for ``owner_id``) take precedence over shared rows.
    """
    if not keys:
        return {}
    rows = (
        await db.execute(
            select(LearnedDecision).where(
                LearnedDecision.kind == kind,
                LearnedDecision.source_key.in_(keys),
                (
                    (LearnedDecision.scope == "shared")
                    | (LearnedDecision.owner_id == owner_id)
                ),
            )
        )
    ).scalars().all()

    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        prev = out.get(r.source_key)
        # personal wins over shared
        if prev is not None and prev["scope"] == "personal" and r.scope == "shared":
            continue
        out[r.source_key] = {
            "id": r.id,
            "scope": r.scope,
            "decision": r.decision,
            "target_field": r.target_field,
            "target_term": r.target_term,
            "target_id": r.target_id,
        }
    return out


async def list_for_owner(db: AsyncSession, owner_id: int) -> list[dict[str, Any]]:
    """A curator's own personal decisions (most recent first)."""
    rows = (
        await db.execute(
            select(LearnedDecision)
            .where(
                LearnedDecision.scope == "personal",
                LearnedDecision.owner_id == owner_id,
            )
            .order_by(LearnedDecision.updated_at.desc())
        )
    ).scalars().all()
    return [_to_dict(r) for r in rows]


async def promotion_candidates(db: AsyncSession, *, min_support: int = 1) -> list[dict[str, Any]]:
    """Personal decisions aggregated for the admin promotion queue.

    Groups agreeing personal rows by ``(kind, source_key, decision, target*)`` and
    reports how many distinct curators confirmed each — the promotion analytics.
    """
    ld = LearnedDecision
    q = (
        select(
            ld.kind, ld.source_key, ld.decision,
            ld.target_field, ld.target_term, ld.target_id,
            func.count(func.distinct(ld.owner_id)).label("curators"),
            func.sum(ld.support_count).label("support"),
        )
        .where(ld.scope == "personal")
        .group_by(ld.kind, ld.source_key, ld.decision,
                  ld.target_field, ld.target_term, ld.target_id)
        .having(func.count(func.distinct(ld.owner_id)) >= min_support)
        .order_by(func.count(func.distinct(ld.owner_id)).desc())
    )
    # Exclude candidates already promoted to shared.
    shared = {
        (r.kind, r.source_key)
        for r in (
            await db.execute(
                select(ld.kind, ld.source_key).where(ld.scope == "shared")
            )
        ).all()
    }
    out = []
    for r in (await db.execute(q)).all():
        if (r.kind, r.source_key) in shared:
            continue
        out.append({
            "kind": r.kind, "source_key": r.source_key, "decision": r.decision,
            "target_field": r.target_field, "target_term": r.target_term,
            "target_id": r.target_id, "curators": int(r.curators),
            "support": int(r.support or 0),
        })
    return out


async def promote(
    db: AsyncSession,
    *,
    kind: str,
    source_key: str,
    decision: str,
    admin_id: int,
    target_field: str | None = None,
    target_term: str | None = None,
    target_id: str | None = None,
) -> dict[str, Any]:
    """Upsert a ``shared`` row (admin promotion). Personal rows are left intact
    (they override the shared baseline for their owner — ADR precedence)."""
    stmt = pg_insert(LearnedDecision).values(
        scope="shared", owner_id=None, kind=kind, source_key=source_key,
        decision=decision, target_field=target_field, target_term=target_term,
        target_id=target_id, promoted_by=admin_id, support_count=1,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["kind", "source_key"],
        index_where=text("scope = 'shared'"),
        set_={
            "decision": stmt.excluded.decision,
            "target_field": stmt.excluded.target_field,
            "target_term": stmt.excluded.target_term,
            "target_id": stmt.excluded.target_id,
            "promoted_by": admin_id,
            "updated_at": func.now(),
        },
    ).returning(LearnedDecision.id)
    new_id = (await db.execute(stmt)).scalar_one()
    return {"id": new_id, "scope": "shared", "kind": kind, "source_key": source_key}


def _to_dict(r: LearnedDecision) -> dict[str, Any]:
    return {
        "id": r.id,
        "scope": r.scope,
        "kind": r.kind,
        "source_key": r.source_key,
        "decision": r.decision,
        "target_field": r.target_field,
        "target_term": r.target_term,
        "target_id": r.target_id,
        "support_count": r.support_count,
        "origin_study_id": r.origin_study_id,
    }
