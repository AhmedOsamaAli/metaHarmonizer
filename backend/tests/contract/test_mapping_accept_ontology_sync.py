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
    from app.routers import auth, mappings

    calls: list[dict] = []

    async def fake_rerun(db, **kwargs):
        calls.append(kwargs)
        return {"added": 1, "removed": 0}

    monkeypatch.setattr(mappings, "rerun_column_ontology", fake_rerun)

    app = FastAPI()
    install_observability(app)
    app.include_router(auth.router)
    app.include_router(mappings.router)

    def make_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    yield make_client, domain, calls

    async with db_session.SessionLocal() as db:
        await db.execute(sa.delete(Study).where(Study.id.like("accept_sync_%")))
        await db.execute(sa.delete(User).where(User.email.like(f"%@{domain}")))
        await db.commit()
    await engine.dispose()
    redis_mod._client = None


async def _seed(owner_id: int) -> tuple[str, list[int]]:
    study_id = f"accept_sync_{uuid.uuid4().hex[:8]}"
    async with db_session.SessionLocal() as db:
        db.add(
            Study(
                id=study_id,
                name="accept sync",
                status="review",
                file_path="accept_sync.csv",
                owner_id=owner_id,
            )
        )
        await db.flush()
        rows = [
            Mapping(study_id=study_id, raw_column="site", matched_field="body_site", status="pending"),
            Mapping(study_id=study_id, raw_column="gender", matched_field="sex", status="pending"),
            Mapping(study_id=study_id, raw_column="comment", matched_field="notes", status="pending"),
            Mapping(study_id=study_id, raw_column="unused", matched_field="notes", status="pending"),
        ]
        db.add_all(rows)
        await db.flush()
        ids = [row.id for row in rows]
        await db.commit()
    return study_id, ids


async def test_single_and_batch_accept_sync_approved_fields(env):
    make_client, domain, calls = env
    async with make_client() as client:
        await register_and_login(client, f"admin@{domain}")
        curator = await register_and_login(client, f"curator@{domain}")
        headers = {"Authorization": f"Bearer {curator['access_token']}"}
        _, ids = await _seed(curator["user"]["id"])

        response = await client.post(f"/api/v1/mappings/{ids[0]}/accept", headers=headers)
        assert response.status_code == 200
        assert calls[-1]["raw_column"] == "site"
        assert calls[-1]["old_field"] == calls[-1]["new_field"] == "body_site"

        response = await client.post(
            "/api/v1/mappings/batch",
            headers=headers,
            json={"mapping_ids": ids[1:3], "action": "accepted"},
        )
        assert response.status_code == 200
        assert [(call["raw_column"], call["new_field"]) for call in calls] == [
            ("site", "body_site"),
            ("gender", "sex"),
            ("comment", "notes"),
        ]

        before_reject = len(calls)
        response = await client.post(
            "/api/v1/mappings/batch",
            headers=headers,
            json={"mapping_ids": [ids[3]], "action": "rejected"},
        )
        assert response.status_code == 200
        assert len(calls) == before_reject
