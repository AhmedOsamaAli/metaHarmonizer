"""API schemas for auth (Sprint 3)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    name: str | None = Field(default=None, max_length=200)
    # Optional: request administrator access. Never grants admin directly — the
    # account is created as a curator with a pending request an admin approves.
    request_admin: bool = False


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    # "Remember me": when False the refresh cookie is session-scoped (cleared on
    # browser close) instead of persistent up to the refresh TTL.
    remember: bool = True


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=200)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


class MessageResponse(BaseModel):
    """Generic non-sensitive acknowledgement (kept deliberately vague for the
    email flows so it never reveals whether an address is registered)."""

    message: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str | None = None
    role: str
    is_active: bool
    email_verified: bool
    approved: bool = False
    admin_requested: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ip: str | None = None
    user_agent: str | None = None
    created_at: datetime
    last_seen: datetime | None = None
    current: bool = False


class RoleUpdate(BaseModel):
    role: Literal["curator", "admin"]


class ActiveUpdate(BaseModel):
    is_active: bool


class ApiTokenCreate(BaseModel):
    scope: Literal["read", "write"] = "read"


class ApiTokenInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scope: str
    created_at: datetime
    revoked_at: datetime | None = None


class ApiTokenCreated(ApiTokenInfo):
    # The plaintext token, returned exactly once at creation time.
    token: str

