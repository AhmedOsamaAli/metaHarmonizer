"""Rate-limit + idempotency middleware tests against the dev Redis (port 6380).

Driven with an in-process ASGI client inside a single event loop (so the async
Redis client stays on one loop). Skipped automatically if Redis is unreachable.
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
import redis as sync_redis
from fastapi import FastAPI

import app.core.redis as redis_mod
from app.core.limits import install_limits
from app.core.middleware import install_observability
from app.core.security import create_access_token
from app.core.settings import settings

pytestmark = pytest.mark.asyncio

REDIS_TEST_URL = "redis://127.0.0.1:6380/0"


def _redis_up() -> bool:
    try:
        sync_redis.from_url(REDIS_TEST_URL, socket_connect_timeout=2).ping()
        return True
    except Exception:
        return False


skip_no_redis = pytest.mark.skipif(not _redis_up(), reason="dev Redis not reachable (port 6380)")


@pytest_asyncio.fixture
async def _redis_clean():
    r = sync_redis.from_url(REDIS_TEST_URL, decode_responses=True)
    for pattern in ("ratelimit:*", "idem:*", "ops:active-users:*"):
        for k in r.scan_iter(pattern):
            r.delete(k)
    redis_mod._client = None  # rebuild async singleton in the running loop
    yield
    for pattern in ("ratelimit:*", "idem:*", "ops:active-users:*"):
        for k in r.scan_iter(pattern):
            r.delete(k)
    # Close the async singleton on its own loop to avoid GC-time warnings.
    if redis_mod._client is not None:
        await redis_mod._client.aclose()
        redis_mod._client = None


def _app() -> FastAPI:
    app = FastAPI()
    install_observability(app)
    install_limits(app)
    calls = {"n": 0}

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    @app.get("/api/v1/jobs/example")
    async def poll_job():
        return {"state": "running"}

    @app.post("/studies")
    async def create_study():
        calls["n"] += 1
        return {"created": calls["n"]}

    app.state._calls = calls
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@skip_no_redis
async def test_anonymous_rate_limit_returns_429(_redis_clean, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_anon", 2)
    limit = settings.rate_limit_anon
    app = _app()
    async with _client(app) as client:
        for _ in range(limit):
            assert (await client.get("/ping")).status_code == 200
        r = await client.get("/ping")
    assert r.status_code == 429
    assert r.headers["Retry-After"]
    assert r.json()["error"]["code"] == "RATE_LIMITED"


@skip_no_redis
async def test_valid_access_token_uses_authenticated_budget(_redis_clean, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_anon", 2)
    monkeypatch.setattr(settings, "rate_limit_auth", 5)
    app = _app()
    token = create_access_token(user_id=123, role="curator", email="audit@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    async with _client(app) as client:
        responses = [
            await client.get("/ping", headers=headers)
            for _ in range(settings.rate_limit_anon + 1)
        ]
    assert all(response.status_code == 200 for response in responses)
    r = sync_redis.from_url(REDIS_TEST_URL, decode_responses=True)
    assert r.zrange("ops:active-users:5m", 0, -1) == ["user:123"]


@skip_no_redis
async def test_active_user_window_counts_distinct_authenticated_users(_redis_clean):
    app = _app()
    first = create_access_token(user_id=101, role="curator", email="first@example.com")
    second = create_access_token(user_id=202, role="curator", email="second@example.com")
    async with _client(app) as client:
        await client.get("/ping", headers={"Authorization": f"Bearer {first}"})
        await client.get("/ping", headers={"Authorization": f"Bearer {first}"})
        await client.get("/ping", headers={"Authorization": f"Bearer {second}"})
        await client.get("/ping")
    r = sync_redis.from_url(REDIS_TEST_URL, decode_responses=True)
    assert r.zcard("ops:active-users:5m") == 2


@skip_no_redis
async def test_rate_limit_exempt_job_poll_still_tracks_active_user(_redis_clean):
    app = _app()
    token = create_access_token(user_id=303, role="curator", email="jobs@example.com")
    async with _client(app) as client:
        response = await client.get(
            "/api/v1/jobs/example",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200
    r = sync_redis.from_url(REDIS_TEST_URL, decode_responses=True)
    assert r.zrange("ops:active-users:5m", 0, -1) == ["user:303"]


@skip_no_redis
async def test_invalid_bearer_token_stays_on_anonymous_budget(_redis_clean, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_anon", 2)
    monkeypatch.setattr(settings, "rate_limit_auth", 5)
    app = _app()
    headers = {"Authorization": "Bearer not-a-valid-token"}
    async with _client(app) as client:
        responses = [await client.get("/ping", headers=headers) for _ in range(3)]
    assert [response.status_code for response in responses] == [200, 200, 429]


@skip_no_redis
async def test_idempotent_post_replays_cached_response(_redis_clean):
    app = _app()
    headers = {"Idempotency-Key": "abc-123"}
    async with _client(app) as client:
        r1 = await client.post("/studies", headers=headers)
        r2 = await client.post("/studies", headers=headers)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()
    assert app.state._calls["n"] == 1
    assert r2.headers.get("Idempotent-Replayed") == "true"


@skip_no_redis
async def test_idempotency_ignored_without_key(_redis_clean):
    app = _app()
    async with _client(app) as client:
        await client.post("/studies")
        await client.post("/studies")
    assert app.state._calls["n"] == 2
