"""The append-only audit log accepts structured provenance details.

Covers the ``details`` argument added so a study can record the engine bundle
(version + loaded models) that produced it. Skips if Postgres is unreachable.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import AuditEvent

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def session_maker(database_url):
    engine = create_async_engine(database_url, poolclass=sa.pool.NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("dev Postgres not reachable")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    # No manual cleanup: audit_events is append-only (DELETE is blocked by a DB
    # trigger); conftest truncates every table between tests.
    await engine.dispose()


async def test_add_audit_entry_persists_engine_bundle(session_maker):
    from app.repositories import audit as audit_repo

    study_id = f"audittest_{uuid.uuid4().hex[:8]}"
    async with session_maker() as s:
        await audit_repo.add_audit_entry(
            s,
            study_id=study_id,
            action="harmonize.completed",
            new_value="mock 0.4.0",
            details={"engine": "mock", "engine_version": "0.4.0", "models": ["m1"], "mode": "both"},
        )
        await s.commit()

    async with session_maker() as s:
        ev = await s.scalar(sa.select(AuditEvent).where(AuditEvent.study_id == study_id))
    assert ev is not None
    assert ev.action == "harmonize.completed"
    assert ev.details["engine_version"] == "0.4.0"
    assert ev.details["models"] == ["m1"]


async def test_add_audit_entry_merges_curator_into_details(session_maker):
    from app.repositories import audit as audit_repo

    study_id = f"audittest_{uuid.uuid4().hex[:8]}"
    async with session_maker() as s:
        await audit_repo.add_audit_entry(
            s, study_id=study_id, action="accept", curator="alice", details={"note": "x"}
        )
        await s.commit()

    async with session_maker() as s:
        ev = await s.scalar(sa.select(AuditEvent).where(AuditEvent.study_id == study_id))
    assert ev is not None
    assert ev.details["curator"] == "alice"
    assert ev.details["note"] == "x"
