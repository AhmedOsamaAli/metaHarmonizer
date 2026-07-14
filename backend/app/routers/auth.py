"""
Auth router (Sprint 3) — register, login, refresh, logout, sessions, current user.

Token model
  - Access token: short-lived JWT sent in the ``Authorization: Bearer`` header.
  - Refresh token: long-lived JWT in an httpOnly cookie, bound to a row in the
    ``sessions`` table via its ``jti``. The session row is the source of truth
    for revocation, so logout / "revoke this device" takes effect immediately.

Policy
  - Argon2id password hashing.
  - Open signup: the first account is ``admin`` (bootstrap); everyone else is a
    ``curator``. Trusted-domain (ALLOWED_EMAIL_DOMAINS) accounts are approved
    automatically; others need an admin to approve them before first sign-in.
  - Account lockout after LOGIN_MAX_FAILURES consecutive failed logins.
"""

from __future__ import annotations

import jwt
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthError, current_user
from app.core.email import send_password_reset_email, send_verification_email
from app.core.errors import AppError
from app.core.hibp import password_breach_count
from app.core.metrics import AUTH_FAILURES
from app.core.redis import get_redis
from app.core.security import (
    REFRESH_COOKIE,
    create_access_token,
    create_email_verify_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    hash_password,
    new_jti,
    verify_password,
)
from app.core.security import _pw_fingerprint
from app.core.settings import settings
from app.db.models import User
from app.db.session import get_db
from app.repositories import sessions as sessions_repo
from app.repositories import users as users_repo
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SessionOut,
    TokenResponse,
    UserOut,
    VerifyEmailRequest,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# ── Errors ───────────────────────────────────────────────────────────────────
class AccountPendingError(AppError):
    code = "ACCOUNT_PENDING"
    status_code = 403


class EmailTakenError(AppError):
    code = "EMAIL_TAKEN"
    status_code = 409


class EmailNotVerifiedError(AppError):
    code = "EMAIL_NOT_VERIFIED"
    status_code = 403


class InvalidTokenError(AppError):
    code = "INVALID_TOKEN"
    status_code = 400


class AccountLockedError(AppError):
    code = "ACCOUNT_LOCKED"
    status_code = 429


class WeakPasswordError(AppError):
    code = "WEAK_PASSWORD"
    status_code = 422


# ── Helpers ──────────────────────────────────────────────────────────────────
def _domain_allowed(email: str) -> bool:
    domains = settings.allowed_email_domain_list
    if not domains:
        return False  # empty -> registration closed (invite-only)
    return email.split("@")[-1].lower() in domains


def _client_ip(request: Request) -> str | None:
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        max_age=settings.refresh_ttl_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")


async def _issue_tokens(
    db: AsyncSession, response: Response, request: Request, user: User
) -> tuple[TokenResponse, str]:
    """Create a session, set the refresh cookie, return (token, jti)."""
    jti = new_jti()
    await sessions_repo.create_session(
        db,
        user_id=user.id,
        refresh_jti=jti,
        ip=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    _set_refresh_cookie(response, create_refresh_token(user_id=user.id, jti=jti))
    access = create_access_token(user_id=user.id, role=user.role, email=user.email)
    return TokenResponse(access_token=access, user=UserOut.model_validate(user)), jti


# ── Lockout (Redis sliding counter, fail-open) ───────────────────────────────
def _lock_key(email: str) -> str:
    return f"login:fail:{email.lower()}"


async def _is_locked(email: str) -> bool:
    try:
        n = await get_redis().get(_lock_key(email))
        return bool(n) and int(n) >= settings.login_max_failures
    except Exception:
        return False  # fail-open: never lock people out because Redis is down


async def _record_failure(email: str) -> None:
    try:
        r = get_redis()
        key = _lock_key(email)
        n = await r.incr(key)
        if n == 1:
            await r.expire(key, settings.login_lockout_min * 60)
    except Exception:
        pass


async def _clear_failures(email: str) -> None:
    try:
        await get_redis().delete(_lock_key(email))
    except Exception:
        pass


# ── Routes ───────────────────────────────────────────────────────────────────
@router.post("/register", response_model=MessageResponse, status_code=201)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    if await users_repo.get_by_email(db, body.email):
        raise EmailTakenError("An account with this email already exists.")

    # Reject passwords known to be compromised (HIBP, fail-open on network error).
    if settings.hibp_check and await password_breach_count(body.password) > 0:
        raise WeakPasswordError(
            "This password has appeared in a data breach. Please choose a different one."
        )

    # Registration is open, and everyone is a curator. Trusted-domain accounts
    # are approved automatically; anyone else (e.g. a personal Gmail) may still
    # register but stays pending until an admin approves them. Admin access is
    # always by request + admin approval, regardless of domain.
    approved_domain = _domain_allowed(body.email)
    is_bootstrap = await users_repo.count_users(db) == 0
    role = "admin" if is_bootstrap else "curator"
    approved = is_bootstrap or approved_domain
    admin_requested = body.request_admin and not is_bootstrap

    user = await users_repo.create_user(
        db,
        email=body.email,
        password_hash=hash_password(body.password),
        name=body.name,
        role=role,
        approved=approved,
        admin_requested=admin_requested,
    )
    # The bootstrap admin is auto-verified so the instance is never locked out
    # before email is configured; everyone else must confirm their address.
    if is_bootstrap:
        user.email_verified = True
    await db.commit()

    if is_bootstrap:
        return MessageResponse(message="Admin account created. You can sign in now.")

    token = create_email_verify_token(user_id=user.id, email=user.email)
    await send_verification_email(to=user.email, name=user.name, token=token)
    if approved:
        message = "Account created. Check your email to verify your address before signing in."
    else:
        message = (
            "Account created. Verify your email — then an administrator will approve "
            "your account before you can sign in."
        )
    return MessageResponse(message=message)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    if await _is_locked(body.email):
        raise AccountLockedError("Too many failed attempts. Try again later.")
    user = await users_repo.get_by_email(db, body.email)
    if (
        not user
        or not user.password_hash
        or not verify_password(body.password, user.password_hash)
    ):
        await _record_failure(body.email)
        AUTH_FAILURES.inc()
        raise AuthError("Incorrect email or password.")
    if not user.is_active:
        raise AuthError("This account is disabled.")
    if not user.email_verified:
        # Credentials are valid but the address isn't confirmed yet — block sign-in
        # and let the client offer to resend the verification email.
        raise EmailNotVerifiedError(
            "Please verify your email address before signing in."
        )
    if not user.approved:
        # Verified, but an untrusted-domain account an admin hasn't approved yet.
        raise AccountPendingError(
            "Your account is awaiting administrator approval."
        )
    await _clear_failures(body.email)
    tokens, _ = await _issue_tokens(db, response, request, user)
    await db.commit()
    return tokens


# ── Email verification + password reset ──────────────────────────────────────
@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    body: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Confirm an email address from the signed token in the verification link."""
    try:
        payload = decode_token(body.token)
    except jwt.PyJWTError:
        raise InvalidTokenError("This verification link is invalid or has expired.")
    if payload.get("type") != "email_verify":
        raise InvalidTokenError("This verification link is invalid.")
    user = await users_repo.get_by_id(db, int(payload.get("sub", 0)))
    if not user:
        raise InvalidTokenError("This verification link is invalid.")
    if not user.email_verified:
        await users_repo.set_email_verified(db, user)
        await db.commit()
    return MessageResponse(message="Email verified. You can now sign in.")


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    body: ResendVerificationRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Resend the verification email. Always returns the same message so it
    can't be used to probe which addresses are registered."""
    user = await users_repo.get_by_email(db, body.email)
    if user and not user.email_verified:
        token = create_email_verify_token(user_id=user.id, email=user.email)
        await send_verification_email(to=user.email, name=user.name, token=token)
    return MessageResponse(
        message="If that address needs verification, we've sent a new link.",
    )


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Send a password-reset link. Always returns the same message regardless of
    whether the address exists (no account enumeration)."""
    user = await users_repo.get_by_email(db, body.email)
    if user and user.password_hash:
        token = create_password_reset_token(
            user_id=user.id, password_hash=user.password_hash
        )
        await send_password_reset_email(to=user.email, name=user.name, token=token)
    return MessageResponse(
        message="If that address has an account, we've sent a reset link.",
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Set a new password from a reset token. The token is single-use: it's bound
    to the old password's fingerprint, so once the password changes it's dead.
    All existing sessions are revoked so a leaked link can't keep access."""
    try:
        payload = decode_token(body.token)
    except jwt.PyJWTError:
        raise InvalidTokenError("This reset link is invalid or has expired.")
    if payload.get("type") != "password_reset":
        raise InvalidTokenError("This reset link is invalid.")
    if settings.hibp_check and await password_breach_count(body.password) > 0:
        raise WeakPasswordError(
            "This password has appeared in a data breach. Please choose a different one."
        )
    user = await users_repo.get_by_id(db, int(payload.get("sub", 0)))
    if not user or payload.get("pwfp") != _pw_fingerprint(user.password_hash):
        raise InvalidTokenError("This reset link is invalid or has already been used.")
    await users_repo.set_password(db, user, hash_password(body.password))
    # Verifying via a reset also confirms control of the inbox.
    if not user.email_verified:
        await users_repo.set_email_verified(db, user)
    await sessions_repo.revoke_all_for_user(db, user.id)
    await db.commit()
    return MessageResponse(message="Password updated. You can now sign in.")


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Change the signed-in user's password after confirming the current one.
    Revokes all other sessions so a change locks out other devices."""
    if not user.password_hash or not verify_password(
        body.current_password, user.password_hash
    ):
        raise AuthError("Your current password is incorrect.")
    if settings.hibp_check and await password_breach_count(body.new_password) > 0:
        raise WeakPasswordError(
            "This password has appeared in a data breach. Please choose a different one."
        )
    await users_repo.set_password(db, user, hash_password(body.new_password))
    await sessions_repo.revoke_all_for_user(db, user.id)
    await db.commit()
    return MessageResponse(message="Password changed. Other devices have been signed out.")


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Exchange a valid refresh cookie for a new access token, rotating the
    underlying session (old refresh token is revoked)."""
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise AuthError("Missing refresh token.")
    try:
        payload = decode_token(raw)
    except jwt.PyJWTError:
        raise AuthError("Invalid or expired refresh token.")
    if payload.get("type") != "refresh":
        raise AuthError("Wrong token type.")

    session = await sessions_repo.get_active_by_jti(db, payload.get("jti", ""))
    if session is None:
        raise AuthError("Session has been revoked.")
    user = await users_repo.get_by_id(db, int(payload["sub"]))
    if not user or not user.is_active:
        raise AuthError("Account not found or disabled.")

    await sessions_repo.revoke_by_jti(db, session.refresh_jti)
    tokens, _ = await _issue_tokens(db, response, request, user)
    await db.commit()
    return tokens


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> Response:
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        try:
            payload = decode_token(raw)
            await sessions_repo.revoke_by_jti(db, payload.get("jti", ""))
            await db.commit()
        except jwt.PyJWTError:
            pass
    _clear_refresh_cookie(response)
    response.status_code = 204
    return response


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SessionOut]:
    """List the caller's active sessions (devices)."""
    current_jti = None
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        try:
            current_jti = decode_token(raw).get("jti")
        except jwt.PyJWTError:
            current_jti = None

    rows = await sessions_repo.list_for_user(db, user.id)
    out: list[SessionOut] = []
    for s in rows:
        item = SessionOut.model_validate(s)
        item.current = s.refresh_jti == current_jti
        out.append(item)
    return out


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke_session(
    session_id: int,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Revoke one of the caller's sessions (remote logout of a device)."""
    await sessions_repo.revoke(db, user_id=user.id, session_id=session_id)
    await db.commit()
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/request-admin", response_model=UserOut)
async def request_admin(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Let a signed-in curator request admin access for an admin to approve.

    Idempotent — sets the pending flag; no-op for admins.
    """
    if user.role == "curator" and not user.admin_requested:
        user.admin_requested = True
        await db.commit()
        await db.refresh(user)
    return UserOut.model_validate(user)

