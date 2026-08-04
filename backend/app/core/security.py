"""
Security primitives: password hashing (Argon2id) and JWT access tokens.

- Passwords are hashed with Argon2id (argon2-cffi defaults are OWASP-sane).
- Access tokens are short-lived signed JWTs (HS256) carrying the user id, role,
  and email. Refresh tokens (Sprint 3 slice 2) live in an httpOnly cookie and
  are tracked server-side in the sessions table.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.settings import settings

_ph = PasswordHasher()

JWT_ALG = "HS256"
API_TOKEN_PREFIX = "mh_"

# Cookie name for the refresh token (httpOnly, not readable by JS).
REFRESH_COOKIE = "mh_refresh"


# ── Passwords ────────────────────────────────────────────────────────────────
def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def needs_rehash(hashed: str) -> bool:
    return _ph.check_needs_rehash(hashed)


# ── Access tokens ────────────────────────────────────────────────────────────
def create_access_token(*, user_id: int, role: str, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "email": email,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_ttl_min)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALG)


def decode_token(token: str) -> dict[str, Any]:
    """Decode + verify a JWT. Raises ``jwt.PyJWTError`` on any problem."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALG])


# ── Email verification + password reset tokens ───────────────────────────────
# Stateless signed JWTs — no DB table needed. The reset token is made single-use
# by binding it to a fingerprint of the current password hash: once the password
# changes the fingerprint no longer matches, so a used (or stale) link is dead.

def _pw_fingerprint(password_hash: str | None) -> str:
    """Short, non-reversible fingerprint of a password hash, embedded in reset
    tokens so they self-invalidate once the password changes."""
    return hashlib.sha256((password_hash or "").encode("utf-8")).hexdigest()[:16]


def create_email_verify_token(*, user_id: int, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "type": "email_verify",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.email_verify_ttl_min)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALG)


def create_password_reset_token(*, user_id: int, password_hash: str | None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "pwfp": _pw_fingerprint(password_hash),
        "type": "password_reset",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.password_reset_ttl_min)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALG)


# ── Refresh tokens ───────────────────────────────────────────────────────────
def new_jti() -> str:
    """A unique, unguessable identifier for a refresh token / session."""
    return secrets.token_urlsafe(32)


def create_refresh_token(*, user_id: int, jti: str, remember: bool = True) -> str:
    """Long-lived signed JWT bound to a server-side session via ``jti``.

    The session row (sessions table) is the source of truth for revocation:
    a refresh token is only honoured while its ``jti`` maps to a live session.
    ``remember`` is carried so the cookie stays session-scoped across refreshes.
    """
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "jti": jti,
        "type": "refresh",
        "remember": remember,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.refresh_ttl_days)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALG)


# ── API tokens (Sprint 3 slice 4) ────────────────────────────────────────────
def generate_api_token() -> tuple[str, str]:
    """Return ``(plaintext, sha256_hash)``. Only the hash is stored; the
    plaintext is shown to the user exactly once."""
    plain = "mh_" + secrets.token_urlsafe(32)
    return plain, hash_api_token(plain)


def hash_api_token(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()
