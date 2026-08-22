"""Auth slice-1 tests: register (domain gate, bootstrap admin), login, /me.

Runs against the isolated ``*_test`` database (truncated between tests), so the
bootstrap-admin path (first user = auto-verified admin) is deterministic.
Skips if Postgres is unreachable.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.core.settings as settings_mod
import app.db.session as db_session
from app.db.models import User

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client(database_url, monkeypatch):
    engine = create_async_engine(database_url, poolclass=sa.pool.NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("dev Postgres not reachable")

    db_session.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    # Reset the Redis singleton so the lockout code binds to this test's loop.
    import app.core.redis as redis_mod

    redis_mod._client = None

    # Allow a unique throwaway domain for this test run.
    domain = f"t{uuid.uuid4().hex[:8]}.example.com"
    monkeypatch.setattr(settings_mod.settings, "allowed_email_domains", domain, raising=False)
    monkeypatch.setattr(settings_mod.settings, "hibp_check", False, raising=False)

    from fastapi import FastAPI
    from app.core.middleware import install_observability
    from app.routers import auth

    app = FastAPI()
    install_observability(app)
    app.include_router(auth.router)

    async def _make_client():
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test")

    yield _make_client, domain, db_session.SessionLocal

    # cleanup created users
    async with db_session.SessionLocal() as s:
        await s.execute(sa.delete(User).where(User.email.like(f"%@{domain}")))
        await s.commit()
    await engine.dispose()
    redis_mod._client = None


async def _register(c, email, password="pw-123456", **extra):
    return await c.post(
        "/api/v1/auth/register", json={"email": email, "password": password, **extra}
    )


async def _login(c, email, password="pw-123456"):
    return await c.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )


async def test_register_login_me_flow(client):
    make_client, domain, _ = client
    email = f"alice@{domain}"
    async with await make_client() as c:
        # First user in a fresh domain bootstraps admin and is auto-verified, so
        # it can sign in immediately (register itself no longer returns a token).
        r = await _register(c, email, "s3cret-pass")
        assert r.status_code == 201, r.text

        r = await _login(c, email, "s3cret-pass")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["user"]["email"] == email
        assert body["user"]["role"] == "admin"
        token = body["access_token"]

        # me with the token
        r = await c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["email"] == email


async def test_second_user_is_curator(client):
    make_client, domain, SessionLocal = client
    async with await make_client() as c:
        await _register(c, f"admin@{domain}")  # bootstrap admin
        await _register(c, f"bob@{domain}")  # curator, needs verification
    async with SessionLocal() as s:
        bob = await s.scalar(sa.select(User).where(User.email == f"bob@{domain}"))
        assert bob.role == "curator"
        assert bob.email_verified is False


async def test_untrusted_domain_registers_pending(client):
    make_client, domain, SessionLocal = client
    async with await make_client() as c:
        # A trusted-domain user bootstraps the admin so the next isn't bootstrap.
        await _register(c, f"admin@{domain}")
        # Registration is open: an untrusted domain still succeeds, but the
        # account lands unapproved (an admin must approve before first sign-in).
        r = await _register(c, "x@gmail.com")
        assert r.status_code == 201, r.text
    async with SessionLocal() as s:
        u = await s.scalar(sa.select(User).where(User.email == "x@gmail.com"))
        assert u is not None
        assert u.role == "curator"
        assert u.approved is False


async def test_wildcard_domain_auto_approves_but_still_requires_verification(
    client, monkeypatch
):
    make_client, domain, SessionLocal = client
    monkeypatch.setattr(
        settings_mod.settings, "allowed_email_domains", "*", raising=False
    )
    email = "open-registration@gmail.com"
    async with await make_client() as c:
        await _register(c, f"admin@{domain}")
        registered = await _register(c, email)
        assert registered.status_code == 201
        assert "verify" in registered.json()["message"].lower()

        blocked = await c.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "pw-123456"},
        )
        assert blocked.status_code == 403
        assert blocked.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"

    async with SessionLocal() as s:
        user = await s.scalar(sa.select(User).where(User.email == email))
        assert user is not None
        assert user.approved is True
        assert user.email_verified is False


async def test_duplicate_email_conflict(client):
    make_client, domain, _ = client
    email = f"dup@{domain}"
    async with await make_client() as c:
        await c.post("/api/v1/auth/register", json={"email": email, "password": "pw-123456"})
        r = await c.post("/api/v1/auth/register", json={"email": email, "password": "pw-123456"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "EMAIL_TAKEN"


async def test_bad_password_rejected(client):
    make_client, domain, _ = client
    email = f"carol@{domain}"
    async with await make_client() as c:
        await c.post("/api/v1/auth/register", json={"email": email, "password": "right-pass"})
        r = await c.post("/api/v1/auth/login", json={"email": email, "password": "wrong-pass"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_FAILED"


async def test_login_fails_closed_when_lockout_store_is_unavailable(client, monkeypatch):
    make_client, domain, _ = client
    email = f"redis-down@{domain}"

    def unavailable_redis():
        raise RuntimeError("redis unavailable")

    import app.routers.auth as auth_mod

    async with await make_client() as c:
        await c.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "right-pass"},
        )
        monkeypatch.setattr(auth_mod, "get_redis", unavailable_redis)
        response = await c.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "right-pass"},
        )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "ACCOUNT_LOCKED"


async def test_me_requires_token(client):
    make_client, domain, _ = client
    async with await make_client() as c:
        r = await c.get("/api/v1/auth/me")
    assert r.status_code == 401


# ── Slice 2: refresh / logout / sessions ─────────────────────────────────────
async def test_login_sets_refresh_cookie(client):
    from app.core.security import REFRESH_COOKIE

    make_client, domain, _ = client
    async with await make_client() as c:
        await _register(c, f"cook@{domain}")  # bootstrap admin, auto-verified
        r = await _login(c, f"cook@{domain}")
        assert r.status_code == 200
        assert REFRESH_COOKIE in c.cookies


async def test_refresh_rotates_and_returns_access(client):
    make_client, domain, _ = client
    async with await make_client() as c:
        await _register(c, f"refr@{domain}")
        await _login(c, f"refr@{domain}")
        r = await c.post("/api/v1/auth/refresh")
        assert r.status_code == 200, r.text
        assert r.json()["access_token"]


async def test_logout_revokes_refresh(client):
    make_client, domain, _ = client
    async with await make_client() as c:
        await _register(c, f"out@{domain}")
        await _login(c, f"out@{domain}")
        r = await c.post("/api/v1/auth/logout")
        assert r.status_code == 204
        # Cookie is cleared, and even a stale refresh token is now rejected.
        r = await c.post("/api/v1/auth/refresh")
        assert r.status_code == 401


async def test_sessions_list_and_revoke(client):
    make_client, domain, _ = client
    async with await make_client() as c:
        reg = await _register(c, f"sess@{domain}")
        assert reg.status_code == 201
        login = await _login(c, f"sess@{domain}")
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # A second login creates a second session for the same user.
        async with await make_client() as c2:
            await c2.post(
                "/api/v1/auth/login",
                json={"email": f"sess@{domain}", "password": "pw-123456"},
            )

        r = await c.get("/api/v1/auth/sessions", headers=headers)
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= 2
        assert any(s["current"] for s in rows)

        # Revoke a non-current session.
        other = next(s for s in rows if not s["current"])
        r = await c.delete(f"/api/v1/auth/sessions/{other['id']}", headers=headers)
        assert r.status_code == 204

        r = await c.get("/api/v1/auth/sessions", headers=headers)
        assert all(s["id"] != other["id"] for s in r.json())


async def test_refresh_without_cookie_rejected(client):
    make_client, domain, _ = client
    async with await make_client() as c:
        r = await c.post("/api/v1/auth/refresh")
    assert r.status_code == 401


# ── Slice 3: email verification + password reset ─────────────────────────────
async def test_login_blocked_until_verified(client, monkeypatch):
    make_client, domain, _ = client
    sent: list[dict] = []

    async def _capture(**kwargs):
        sent.append(kwargs)

    monkeypatch.setattr("app.routers.auth.send_verification_email", _capture)
    async with await make_client() as c:
        await _register(c, f"admin@{domain}")  # bootstrap admin (no email sent)
        await _register(c, f"newbie@{domain}")  # curator -> needs verification
        r = await _login(c, f"newbie@{domain}")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"
    assert sent  # a verification email was attempted for the curator


async def test_verify_email_then_login(client, monkeypatch):
    make_client, domain, _ = client
    tokens: list[str] = []

    async def _capture(*, to, name, token):
        tokens.append(token)

    monkeypatch.setattr("app.routers.auth.send_verification_email", _capture)
    async with await make_client() as c:
        await _register(c, f"admin@{domain}")
        await _register(c, f"vfy@{domain}")
        r = await c.post("/api/v1/auth/verify-email", json={"token": tokens[-1]})
        assert r.status_code == 200, r.text
        r = await _login(c, f"vfy@{domain}")
        assert r.status_code == 200, r.text
        assert r.json()["access_token"]


async def test_verify_email_bad_token(client):
    make_client, domain, _ = client
    async with await make_client() as c:
        r = await c.post("/api/v1/auth/verify-email", json={"token": "not-a-jwt"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_TOKEN"


async def test_forgot_and_reset_password(client, monkeypatch):
    make_client, domain, _ = client
    reset_tokens: list[str] = []

    async def _capture(*, to, name, token):
        reset_tokens.append(token)

    monkeypatch.setattr("app.routers.auth.send_password_reset_email", _capture)
    async with await make_client() as c:
        await _register(c, f"admin@{domain}", "old-pass-123")  # admin, auto-verified

        r = await c.post("/api/v1/auth/forgot-password", json={"email": f"admin@{domain}"})
        assert r.status_code == 200
        assert reset_tokens

        r = await c.post(
            "/api/v1/auth/reset-password",
            json={"token": reset_tokens[-1], "password": "new-pass-456"},
        )
        assert r.status_code == 200, r.text

        # Old password no longer works; the new one does.
        assert (await _login(c, f"admin@{domain}", "old-pass-123")).status_code == 401
        assert (await _login(c, f"admin@{domain}", "new-pass-456")).status_code == 200


async def test_reset_token_single_use(client, monkeypatch):
    make_client, domain, _ = client
    reset_tokens: list[str] = []

    async def _capture(*, to, name, token):
        reset_tokens.append(token)

    monkeypatch.setattr("app.routers.auth.send_password_reset_email", _capture)
    async with await make_client() as c:
        await _register(c, f"admin@{domain}", "old-pass-123")
        await c.post("/api/v1/auth/forgot-password", json={"email": f"admin@{domain}"})
        token = reset_tokens[-1]
        # First use succeeds.
        r = await c.post("/api/v1/auth/reset-password", json={"token": token, "password": "new-pass-456"})
        assert r.status_code == 200
        # Re-using the same link fails (it's bound to the old password's fingerprint).
        r = await c.post("/api/v1/auth/reset-password", json={"token": token, "password": "another-789"})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_TOKEN"


async def test_forgot_password_unknown_email_is_silent(client):
    make_client, domain, _ = client
    async with await make_client() as c:
        r = await c.post(
            "/api/v1/auth/forgot-password", json={"email": f"ghost@{domain}"}
        )
    # No account enumeration: same 200 + message whether or not the user exists.
    assert r.status_code == 200
