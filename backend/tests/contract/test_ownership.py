"""Per-owner study isolation (task a).

Every upload is one curator's private study — two curators never share one, even
for the same file. So a curator may read and mutate only their own studies:
another curator gets 404 (existence is hidden, never 403, so the sequential
mapping ids behind a study can't be probed), while an admin may read any study
for operator oversight. Skipped if Postgres is down.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.core.settings as settings_mod
import app.db.session as db_session
from app.db.models import Mapping, Study, User

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

    db_session.engine = engine
    db_session.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    import app.core.redis as redis_mod

    redis_mod._client = None

    domain = f"t{uuid.uuid4().hex[:8]}.example.com"
    monkeypatch.setattr(settings_mod.settings, "allowed_email_domains", domain, raising=False)
    monkeypatch.setattr(settings_mod.settings, "hibp_check", False, raising=False)
    monkeypatch.setattr(settings_mod.settings, "auth_mode", "jwt", raising=False)

    from fastapi import FastAPI
    from app.core.middleware import install_observability
    from app.routers import auth, harmonize, mappings

    app = FastAPI()
    install_observability(app)
    app.include_router(auth.router)
    app.include_router(harmonize.router)
    app.include_router(mappings.router)

    def make_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    yield make_client, domain

    async with db_session.SessionLocal() as s:
        await s.execute(sa.delete(User).where(User.email.like(f"%@{domain}")))
        await s.commit()
    await engine.dispose()
    redis_mod._client = None


async def _seed_study(owner_id: int) -> tuple[str, int]:
    """A curator's study with one pending mapping."""
    sid = f"own_{uuid.uuid4().hex[:8]}"
    async with db_session.SessionLocal() as s:
        s.add(Study(id=sid, name="owned", status="review", file_path=None, owner_id=owner_id))
        await s.flush()
        m = Mapping(study_id=sid, raw_column="gender", matched_field="sex",
                    confidence_score=0.9, status="pending")
        s.add(m)
        await s.flush()
        mid = m.id
        await s.commit()
    return sid, mid


async def test_reads_and_writes_are_owner_scoped(env):
    make_client, domain = env
    async with make_client() as c:
        admin = await register_and_login(c, f"admin@{domain}")   # 1st -> admin
        a = await register_and_login(c, f"a@{domain}")           # curator A (owner)
        b = await register_and_login(c, f"b@{domain}")           # curator B (intruder)

        sid, mid = await _seed_study(a["user"]["id"])

        ah = {"Authorization": f"Bearer {a['access_token']}"}
        bh = {"Authorization": f"Bearer {b['access_token']}"}
        adminh = {"Authorization": f"Bearer {admin['access_token']}"}

        # Owner reads their own study + mappings.
        assert (await c.get(f"/api/v1/mappings/{sid}", headers=ah)).status_code == 200
        assert (await c.get(f"/api/v1/studies/{sid}", headers=ah)).status_code == 200

        # A different curator is denied — 404 (existence hidden), never 403.
        assert (await c.get(f"/api/v1/mappings/{sid}", headers=bh)).status_code == 404
        assert (await c.get(f"/api/v1/studies/{sid}", headers=bh)).status_code == 404

        # Unauthenticated read is rejected.
        assert (await c.get(f"/api/v1/mappings/{sid}")).status_code == 401

        # Writes: another curator can't accept the owner's mapping by guessing its id.
        assert (await c.post(f"/api/v1/mappings/{mid}/accept", headers=bh)).status_code == 404

        # The owner can accept it.
        assert (await c.post(f"/api/v1/mappings/{mid}/accept", headers=ah)).status_code == 200

        # Admins may read any study (operator oversight).
        assert (await c.get(f"/api/v1/studies/{sid}", headers=adminh)).status_code == 200
