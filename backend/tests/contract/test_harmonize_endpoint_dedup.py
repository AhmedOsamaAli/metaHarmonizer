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
from app.db.models import JobRun, Study, User

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


async def test_harmonize_enforces_per_user_quota_but_allows_dedup(env, monkeypatch):
    make_client, domain = env
    monkeypatch.setattr(
        settings_mod.settings, "job_max_active_per_user", 1, raising=False
    )

    async with make_client() as c:
        user = await register_and_login(c, f"quota@{domain}")
        headers = {"Authorization": f"Bearer {user['access_token']}"}
        first = {
            "files": {"file": ("first.csv", b"SEX\nMale\n", "text/csv")},
            "data": {"mode": "schema"},
        }
        distinct = {
            "files": {"file": ("second.csv", b"SEX\nFemale\n", "text/csv")},
            "data": {"mode": "schema"},
        }

        created = await c.post("/api/v1/harmonize", headers=headers, **first)
        assert created.status_code == 202, created.text

        duplicate = await c.post("/api/v1/harmonize", headers=headers, **first)
        assert duplicate.status_code == 202, duplicate.text
        assert duplicate.json()["study_id"] == created.json()["study_id"]

        rejected = await c.post("/api/v1/harmonize", headers=headers, **distinct)
        assert rejected.status_code == 429, rejected.text
        assert rejected.headers["Retry-After"] == "30"


async def test_queue_failure_cleans_upload_and_releases_dedup(env, monkeypatch):
    make_client, domain = env
    stored: set[str] = set()
    failed_study_id: str | None = None

    class FakeStorage:
        scheme = "s3"

        def store(self, key, _src):
            stored.add(key)

        def delete(self, key):
            stored.discard(key)

    async def fail_enqueue(**kwargs):
        nonlocal failed_study_id
        failed_study_id = kwargs["study_id"]
        raise RuntimeError("queue unavailable")

    import app.routers.harmonize as harmonize_mod

    monkeypatch.setattr(harmonize_mod, "get_storage", lambda: FakeStorage())
    monkeypatch.setattr(harmonize_mod, "enqueue_harmonize", fail_enqueue)

    csv = b"SEX,AGE\nMale,61\n"
    submit = {
        "files": {"file": ("queue-failure.csv", csv, "text/csv")},
        "data": {"mode": "schema"},
    }

    async with make_client() as c:
        user = await register_and_login(c, f"queue@{domain}")
        headers = {"Authorization": f"Bearer {user['access_token']}"}

        failed = await c.post("/api/v1/harmonize", headers=headers, **submit)
        assert failed.status_code == 503, failed.text
        assert stored == set()
        assert failed_study_id is not None

        async def succeed_enqueue(**_kwargs):
            return None

        monkeypatch.setattr(harmonize_mod, "enqueue_harmonize", succeed_enqueue)
        retried = await c.post("/api/v1/harmonize", headers=headers, **submit)
        assert retried.status_code == 202, retried.text
        retried_study_id = retried.json()["study_id"]
        assert retried_study_id != failed_study_id

    async with db_session.SessionLocal() as s:
        studies = list(
            await s.scalars(
                sa.select(Study)
                .where(Study.id.in_([failed_study_id, retried_study_id]))
                .order_by(Study.created_at)
            )
        )
        assert [study.status for study in studies] == ["failed", "queued"]
        failed_job = await s.scalar(
            sa.select(JobRun).where(JobRun.study_id == studies[0].id)
        )
        assert failed_job is not None
        assert failed_job.state == "failed"
        assert failed_job.error_code == "queue_unavailable"
