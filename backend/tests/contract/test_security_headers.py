"""Security headers are present on every response (defense-in-depth).

These run without a database — they only exercise the middleware stack via an
in-process ASGI client against the dependency-free liveness endpoint.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client() -> httpx.AsyncClient:
    from app.main import app

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_security_headers_present(client):
    async with client as c:
        r = await c.get("/healthz")
    assert r.status_code == 200
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in r.headers["Permissions-Policy"]
    assert r.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    # Plain HTTP must NOT advertise HSTS (would pin an un-servable https upgrade).
    assert "Strict-Transport-Security" not in r.headers


async def test_hsts_only_behind_https(client):
    async with client as c:
        r = await c.get("/healthz", headers={"x-forwarded-proto": "https"})
    assert "max-age=" in r.headers.get("Strict-Transport-Security", "")
