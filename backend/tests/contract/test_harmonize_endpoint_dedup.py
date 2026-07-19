"""Endpoint-level harmonize idempotency test.

Drives ``POST /api/v1/harmonize`` twice with the SAME file and asserts the second
submit is deduped to the first study's in-flight job. This exercises the router's
content-hash fast path end-to-end (hash, lookup, existing-job response) — the
DB-index race guard is covered separately in test_harmonize_dedup.py.

The pipeline is stubbed (no engine/Redis): ``enqueue_harmonize`` is a no-op so the
study stays in the active window between the two requests, and ``has_capacity``
always passes.

Skipped if Postgres is unreachable.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.core.settings as settings_mod
import app.db.session as db_session
from app.db.models import Study, User

from _authflow import register_and_login

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def env(database_url, monkeypatch):
    engine = create_async_engine(database_url, poolclass=sa.pool.NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("dev Postgres not reachable")

    db_session.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    import app.core.redis as redis_mod

    redis_mod._client = None

    domain = f"t{uuid.uuid4().hex[:8]}.example.com"
    monkeypatch.setattr(settings_mod.settings, "allowed_email_domains", domain, raising=False)
    monkeypatch.setattr(settings_mod.settings, "hibp_check", False, raising=False)

    # Stub the pipeline: no worker advances the study, so it stays in the active
    # (pending/queued) window between the two submits, and no Redis/engine is hit.
    async def _noop_enqueue(**_kwargs):
        return None

    async def _always_capacity():
        return True

    import app.routers.harmonize as harmonize_mod

    monkeypatch.setattr(harmonize_mod, "enqueue_harmonize", _noop_enqueue)
    monkeypatch.setattr(harmonize_mod, "has_capacity", _always_capacity)

    from fastapi import FastAPI

    from app.core.middleware import install_observability
    from app.routers import auth, harmonize

    app = FastAPI()
    install_observability(app)
    app.include_router(auth.router)
    app.include_router(harmonize.router)

    def make_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    yield make_client, domain

    async with db_session.SessionLocal() as s:
        await s.execute(sa.delete(User).where(User.email.like(f"%@{domain}")))
        await s.commit()
    await engine.dispose()
    redis_mod._client = None


async def test_harmonize_double_submit_is_deduped(env):
    make_client, domain = env
    csv = b"SEX,AGE\nMale,61\nFemale,47\n"
    submit = {
        "files": {"file": ("study.csv", csv, "text/csv")},
        "data": {"mode": "schema"},
    }

    async with make_client() as c:
        user = await register_and_login(c, f"admin@{domain}")  # first -> admin (has curator)
        headers = {"Authorization": f"Bearer {user['access_token']}"}

        r1 = await c.post("/api/v1/harmonize", headers=headers, **submit)
        assert r1.status_code == 202, r1.text
        sid1 = r1.json()["study_id"]

        r2 = await c.post("/api/v1/harmonize", headers=headers, **submit)
        assert r2.status_code == 202, r2.text
        sid2 = r2.json()["study_id"]

        # Identical content -> deduped to the same in-flight study, not a new one.
        assert sid2 == sid1
        assert "already being harmonized" in r2.json()["message"].lower()

    async with db_session.SessionLocal() as s:
        count = await s.scalar(
            sa.select(sa.func.count()).select_from(Study).where(Study.id == sid1)
        )
        assert count == 1
        await s.execute(sa.delete(Study).where(Study.id == sid1))
        await s.commit()
