"""Review-queue endpoint test (G7) — real app + Postgres via httpx ASGI.

Verifies the active-learning ordering over the real route: pending mappings are
returned risky-first with look-alikes grouped, and stats report batchable
groups. Skipped if Postgres is down.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.core.settings as settings_mod
import app.db.session as db_session
from app.db.models import Mapping, Study

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def queue_app(database_url, monkeypatch):
    engine = create_async_engine(database_url, poolclass=sa.pool.NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("dev Postgres not reachable")

    # The review-queue read is now owner-scoped (requires an authenticated user).
    # This test targets queue ORDERING, not auth, so run with auth disabled — the
    # synthetic admin then satisfies the guard without a token round-trip.
    monkeypatch.setattr(settings_mod.settings, "auth_mode", "none", raising=False)

    db_session.engine = engine
    db_session.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    study_id = f"alq_{uuid.uuid4().hex[:8]}"
    async with db_session.SessionLocal() as s:
        s.add(Study(id=study_id, name="AL Queue", status="review", file_path=None))
        await s.flush()
        # A safe singleton + a risky look-alike group of 3 (all -> body_site).
        s.add(Mapping(study_id=study_id, raw_column="gender", matched_field="sex",
                      confidence_score=0.98, status="pending"))
        for i, c in enumerate([0.55, 0.60, 0.58]):
            s.add(Mapping(study_id=study_id, raw_column=f"site_{i}",
                          matched_field="body_site", confidence_score=c, status="pending"))
        # A reviewed one must be excluded from the queue.
        s.add(Mapping(study_id=study_id, raw_column="age", matched_field="age",
                      confidence_score=0.5, status="accepted"))
        await s.commit()

    from fastapi import FastAPI
    from app.core.middleware import install_observability
    from app.routers import mappings as mappings_router

    app = FastAPI()
    install_observability(app)
    app.include_router(mappings_router.router)

    yield app, study_id

    async with db_session.SessionLocal() as s:
        await s.execute(sa.text("DELETE FROM mappings WHERE study_id = :sid"), {"sid": study_id})
        await s.execute(sa.text("DELETE FROM studies WHERE id = :sid"), {"sid": study_id})
        await s.commit()
    await engine.dispose()


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_review_queue_orders_risky_grouped(queue_app):
    app, study_id = queue_app
    async with _client(app) as client:
        r = await client.get(f"/api/v1/mappings/{study_id}/review-queue")
    assert r.status_code == 200
    body = r.json()
    items = body["items"]

    # Only the 4 pending rows (accepted one excluded).
    assert len(items) == 4
    assert all(m["status"] == "pending" for m in items)

    # Risky body_site group leads; the safe sex singleton is last.
    assert items[0]["group_key"] == "body_site"
    assert items[-1]["group_key"] == "sex"

    # The three body_site rows are contiguous (grouped, not scattered).
    keys = [m["group_key"] for m in items]
    assert keys == ["body_site", "body_site", "body_site", "sex"]

    # Stats report the batchable group.
    assert body["stats"]["pending"] == 4
    assert body["stats"]["batchable_groups"] == 1
    assert body["stats"]["risky"] == 3
