"""Audit query endpoint tests (U11) against the dev Postgres.

Inserts audit events directly (the log is append-only) and exercises the
cursor-paginated GET /api/v1/audit with filters. Skipped if Postgres is down.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.db.session as db_session
from app.db.models import AuditEvent

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def app_and_study(database_url):
    engine = create_async_engine(database_url, poolclass=sa.pool.NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("dev Postgres not reachable")

    # Point the app's session factory at this engine.
    db_session.engine = engine
    db_session.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    study_id = f"audit_{uuid.uuid4().hex[:8]}"
    async with db_session.SessionLocal() as s:
        for i in range(3):
            s.add(AuditEvent(study_id=study_id, action="accept", new_value=str(i)))
        s.add(AuditEvent(study_id=study_id, action="reject", new_value="x"))
        await s.commit()

    # Build the app after the session factory is patched.
    from fastapi import FastAPI
    from app.core.middleware import install_observability
    from app.core.deps import current_user
    from app.db.models import User
    from app.routers import audit

    app = FastAPI()
    install_observability(app)
    app.include_router(audit.router)
    # The audit endpoint is admin-only; inject a synthetic admin so the test
    # exercises the query logic without a full auth handshake.
    app.dependency_overrides[current_user] = lambda: User(
        id=1, email="admin@test.local", role="admin"
    )

    yield app, study_id

    # NB: audit_events is append-only (DB trigger blocks DELETE) — by design
    # we cannot clean these rows. Each test uses a unique study_id so the tiny
    # number of leftover rows never affects assertions.
    await engine.dispose()


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_filter_by_study_and_action(app_and_study):
    app, study_id = app_and_study
    async with _client(app) as client:
        r = await client.get("/api/v1/audit", params={"study_id": study_id, "action": "accept"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 3
    assert all(e["action"] == "accept" for e in body["items"])


async def test_cursor_pagination_walks_all_events(app_and_study):
    app, study_id = app_and_study
    seen: list[int] = []
    async with _client(app) as client:
        cursor = None
        for _ in range(5):  # safety bound
            params = {"study_id": study_id, "limit": 2}
            if cursor:
                params["cursor"] = cursor
            r = await client.get("/api/v1/audit", params=params)
            body = r.json()
            seen += [e["id"] for e in body["items"]]
            cursor = body["next_cursor"]
            if not cursor:
                break
    # 4 events total for the study, newest-first, no duplicates.
    assert len(seen) == 4
    assert seen == sorted(seen, reverse=True)
    assert len(set(seen)) == 4
