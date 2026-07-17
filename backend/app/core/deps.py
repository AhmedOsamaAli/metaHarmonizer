"""
Auth dependencies shared across routers.

``current_user`` resolves the Bearer access token to a ``User``. ``require_role``
builds a dependency that additionally enforces a minimum role. When
``AUTH_MODE=none`` (local dev / CI without auth) a synthetic admin user is
returned so protected routes stay reachable.
"""

from __future__ import annotations

import jwt
from fastapi import Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import decode_token, hash_api_token
from app.core.settings import settings
from app.db.models import User
from app.db.session import get_db
from app.repositories import api_tokens as api_tokens_repo
from app.repositories import users as users_repo

# Role hierarchy: higher number = more privilege.
ROLE_RANK = {"curator": 1, "admin": 2}

# API-token prefix (see app.core.security.generate_api_token).
API_TOKEN_PREFIX = "mh_"


class AuthError(AppError):
    code = "AUTH_FAILED"
    status_code = 401


class ForbiddenError(AppError):
    code = "FORBIDDEN"
    status_code = 403


# Stable identity for the AUTH_MODE=none admin.
_DEV_ADMIN_EMAIL = "dev@localhost"


async def _ensure_dev_admin(db: AsyncSession) -> User:
    """Return the real, persisted admin used when AUTH_MODE=none.

    A purely synthetic in-memory user (id=0) can authenticate, but anything it
    owns -- e.g. ``studies.owner_id`` -- is a foreign key into ``users.id`` and
    would fail with a FK violation on insert. So fetch-or-create a genuine row
    the first time and reuse it after. It has no password (login is disabled).
    """
    user = await users_repo.get_by_email(db, _DEV_ADMIN_EMAIL)
    if user is None:
        try:
            user = await users_repo.create_user(
                db,
                email=_DEV_ADMIN_EMAIL,
                password_hash=None,
                name="Dev (auth disabled)",
                role="admin",
                approved=True,
            )
            await users_repo.set_email_verified(db, user)
            await db.commit()
        except IntegrityError:
            # A concurrent first request already created it -- reuse that row.
            await db.rollback()
            user = await users_repo.get_by_email(db, _DEV_ADMIN_EMAIL)
    return user


async def _user_from_api_token(request: Request, db: AsyncSession, token: str) -> User:
    """Resolve a personal API token (Bearer ``mh_...``) to its owner."""
    record = await api_tokens_repo.get_active_by_hash(db, hash_api_token(token))
    if record is None:
        raise AuthError("Invalid or revoked API token.")
    user = await users_repo.get_by_id(db, record.user_id)
    if not user or not user.is_active:
        raise AuthError("Account not found or disabled.")
    request.state.user_id = user.id
    request.state.token_scope = record.scope  # "read" | "write"
    return user


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Resolve the authenticated user from a Bearer credential.

    Accepts either a short-lived access JWT or a personal API token
    (``mh_...``). When ``AUTH_MODE=none`` a synthetic admin is returned.
    """
    if settings.auth_mode == "none":
        user = await _ensure_dev_admin(db)
        request.state.user_id = user.id
        request.state.token_scope = "write"
        return user

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise AuthError("Missing bearer token.")
    token = auth[7:]

    if token.startswith(API_TOKEN_PREFIX):
        return await _user_from_api_token(request, db, token)

    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        raise AuthError("Invalid or expired token.")
    if payload.get("type") != "access":
        raise AuthError("Wrong token type.")

    user = await users_repo.get_by_id(db, int(payload["sub"]))
    if not user or not user.is_active:
        raise AuthError("Account not found or disabled.")
    request.state.user_id = user.id
    # Interactive sessions have full write scope.
    request.state.token_scope = "write"
    return user


def require_role(minimum: str):
    """Return a dependency that requires at least ``minimum`` role."""
    threshold = ROLE_RANK[minimum]

    async def _checker(user: User = Depends(current_user)) -> User:
        if ROLE_RANK.get(user.role, 0) < threshold:
            raise ForbiddenError(f"Requires '{minimum}' role or higher.")
        return user

    return _checker


def actor_label(user: User) -> str:
    """Human-readable label for audit rows (the user's name, else email)."""
    return getattr(user, "name", None) or getattr(user, "email", None) or "user"


def require_scope(scope: str):
    """Return a dependency requiring a token scope (``read`` < ``write``).

    Interactive (JWT) sessions always have ``write``; API tokens carry the
    scope chosen at creation time.
    """

    async def _checker(request: Request, user: User = Depends(current_user)) -> User:
        granted = getattr(request.state, "token_scope", "write")
        if scope == "write" and granted != "write":
            raise ForbiddenError("This API token is read-only.")
        return user

    return _checker
