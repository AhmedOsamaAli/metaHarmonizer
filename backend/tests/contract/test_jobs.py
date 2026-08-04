"""Sprint-4 tests: job_runs lifecycle, WS ticket auth, cancel flags, job endpoints.

Avoids importing the harmonize router (pandas) so it runs in the lightweight
test venv. Skips gracefully if Postgres/Redis are down.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.core.settings as settings_mod
import app.db.session as db_session
from app.db.models import JobFailure, JobRun, User

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
    try:
        await redis_mod.get_redis().ping()
    except Exception:
        await engine.dispose()
        pytest.skip("dev Redis not reachable")

    domain = f"t{uuid.uuid4().hex[:8]}.example.com"
    monkeypatch.setattr(settings_mod.settings, "allowed_email_domains", domain, raising=False)
    monkeypatch.setattr(settings_mod.settings, "hibp_check", False, raising=False)

    from fastapi import FastAPI
    from app.core.middleware import install_observability
    from app.routers import auth, ws

    app = FastAPI()
    install_observability(app)
    app.include_router(auth.router)
    app.include_router(ws.router)

    def make_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    yield make_client, domain

    async with db_session.SessionLocal() as s:
        await s.execute(sa.delete(JobFailure))
        await s.execute(sa.delete(JobRun).where(JobRun.study_id.like("jobtest_%")))
        await s.execute(sa.delete(User).where(User.email.like(f"%@{domain}")))
        await s.commit()
    await engine.dispose()
    redis_mod._client = None


# ── job_runs lifecycle ────────────────────────────────────────────────────────
async def test_job_lifecycle_success(env):
    from app.repositories import jobs as jobs_repo

    study_id = f"jobtest_{uuid.uuid4().hex[:8]}"
    async with db_session.SessionLocal() as s:
        job = await jobs_repo.create_job(s, study_id=study_id, kind="harmonize")
        assert job.state == "queued" and job.attempt == 0
        await jobs_repo.mark_running(s, job)
        assert job.state == "running" and job.attempt == 1
        await jobs_repo.mark_succeeded(s, job)
        assert job.state == "succeeded" and job.finished_at is not None
        await s.commit()


async def test_job_failure_dead_letters_after_retries(env):
    from app.repositories import jobs as jobs_repo

    study_id = f"jobtest_{uuid.uuid4().hex[:8]}"
    async with db_session.SessionLocal() as s:
        job = await jobs_repo.create_job(s, study_id=study_id, kind="harmonize")
        await jobs_repo.mark_running(s, job)
        await jobs_repo.mark_failed(
            s, job, error_code="ENGINE_ERROR", error_message="boom", dead_letter=True
        )
        await s.commit()
        jid = job.id

    async with db_session.SessionLocal() as s:
        dl = await s.scalar(sa.select(JobFailure).where(JobFailure.job_run_id == jid))
        assert dl is not None and dl.error_code == "ENGINE_ERROR"


async def test_latest_for_study(env):
    from app.repositories import jobs as jobs_repo

    study_id = f"jobtest_{uuid.uuid4().hex[:8]}"
    async with db_session.SessionLocal() as s:
        await jobs_repo.create_job(s, study_id=study_id, kind="harmonize")
        await s.commit()
        latest = await jobs_repo.latest_for_study(s, study_id)
        assert latest is not None and latest.study_id == study_id


# ── cancel flags ──────────────────────────────────────────────────────────────
async def test_cancel_flag_roundtrip(env):
    from app.core import jobs as jobcore

    study_id = f"jobtest_{uuid.uuid4().hex[:8]}"
    assert await jobcore.is_cancelled(study_id) is False
    await jobcore.request_cancel(study_id)
    assert await jobcore.is_cancelled(study_id) is True
    await jobcore.clear_cancel(study_id)
    assert await jobcore.is_cancelled(study_id) is False


# ── WS tickets ────────────────────────────────────────────────────────────────
async def test_ws_ticket_is_one_time(env):
    from app.core import jobs as jobcore

    ticket = await jobcore.mint_ws_ticket(42)
    assert await jobcore.redeem_ws_ticket(ticket) == 42
    # Second redeem fails — one-time use.
    assert await jobcore.redeem_ws_ticket(ticket) is None


async def test_ws_ticket_endpoint_requires_auth(env):
    make_client, domain = env
    async with make_client() as c:
        r = await c.post("/api/v1/ws/ticket")
        assert r.status_code == 401

        reg = await register_and_login(c, f"wt@{domain}")
        tok = reg["access_token"]
        r = await c.post("/api/v1/ws/ticket", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        assert len(r.json()["ticket"]) > 20


async def test_job_status_endpoint(env):
    from app.repositories import jobs as jobs_repo
    from app.db.models import Study

    make_client, domain = env
    study_id = f"jobtest_{uuid.uuid4().hex[:8]}"
    async with make_client() as c:
        reg = await register_and_login(c, f"js@{domain}")
        tok = reg["access_token"]
        # job_status is owner-scoped, so seed a study owned by this user.
        async with db_session.SessionLocal() as s:
            s.add(Study(id=study_id, name="job", status="queued",
                        file_path=None, owner_id=reg["user"]["id"]))
            await s.flush()
            await jobs_repo.create_job(s, study_id=study_id, kind="harmonize")
            await s.commit()
        r = await c.get(f"/api/v1/jobs/{study_id}", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        assert r.json()["state"] == "queued"
