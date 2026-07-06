"""
Application settings — the single source of configuration truth.

Loaded once from environment variables (and an optional ``.env`` for local dev)
via pydantic-settings. Importing ``settings`` anywhere returns the same cached
instance. Boot fails loudly (ValidationError) if a required var is missing or a
value is invalid — there is no silent default for security-critical settings.

Mirrors the catalogue in ``.env.example``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The value shipped in .env.example — rejected at boot so a real deployment can
# never run with a publicly-known signing key.
_PLACEHOLDER_JWT_SECRET = "change-me-in-prod-min-32-bytes-long-string"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Engine ──────────────────────────────────────────────────────────────
    engine_impl: Literal["metaharmonizer", "mock"] = "metaharmonizer"
    method_model_yaml: str | None = None
    llm_threshold: float = 0.5
    gemini_api_key: str | None = None
    umls_api_key: str | None = None

    # ── Datastore / cache ───────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://mh:mh_dev_password@localhost:5432/metaharmonizer",
        description="Async SQLAlchemy Postgres DSN.",
    )
    redis_url: str = Field(default="redis://localhost:6379/0")

    # ── Job pipeline (Sprint 4) ─────────────────────────────────────────────
    # inline: run harmonize in a thread off the request path (dev — just uvicorn).
    # queue : enqueue to arq workers for horizontal scale (production).
    job_mode: Literal["inline", "queue"] = "inline"
    job_soft_timeout_sec: int = 300   # 5 min — graceful
    job_hard_timeout_sec: int = 900   # 15 min — worker killed
    job_max_attempts: int = 3
    ws_ticket_ttl_sec: int = 30       # one-time WS auth nonce lifetime

    # ── Object storage ──────────────────────────────────────────────────────
    object_store_url: str = "file:///app/data/objects"
    object_store_endpoint: str | None = None   # S3-compatible endpoint (e.g. R2)
    r2_bucket: str | None = None
    r2_key: str | None = None
    r2_secret: str | None = None

    # ── Auth / security ─────────────────────────────────────────────────────
    auth_mode: Literal["jwt", "none"] = "jwt"
    jwt_secret: str = Field(
        default=_PLACEHOLDER_JWT_SECRET,
        description="HMAC signing key; must be >= 32 bytes and changed from the default when AUTH_MODE=jwt.",
    )
    access_ttl_min: int = 15
    refresh_ttl_days: int = 30
    allowed_email_domains: str = ""  # comma-separated; empty -> admin-invite-only
    resend_api_key: str | None = None
    # Email sending (verification + password reset). When resend_api_key is unset
    # in a non-production env, links are logged instead of sent (dev convenience).
    email_from: str = "MetaHarmonizer <onboarding@resend.dev>"
    app_base_url: str = "http://localhost:5173"
    email_verify_ttl_min: int = 24 * 60  # 24h
    password_reset_ttl_min: int = 30
    # Set true in production (HTTPS) so the refresh cookie is Secure-only.
    cookie_secure: bool = False
    # Lock an account after this many consecutive failed logins.
    login_max_failures: int = 5
    login_lockout_min: int = 15
    # Reject signups whose password appears in a known breach (HIBP, fail-open).
    hibp_check: bool = True

    # ── Web / CORS ──────────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    # ── Rate limiting (spec §6.4) ───────────────────────────────────────────
    # Sliding-window budgets per identity (user id when authenticated, else IP).
    # The authenticated budget must comfortably cover an interactive dashboard
    # session: page loads fan out to several endpoints and live job progress is
    # polled, so a tight budget would 429 legitimate use. Anonymous traffic
    # (login/register) stays small to blunt credential-stuffing.
    rate_limit_auth: int = 600
    rate_limit_anon: int = 20
    rate_limit_window_sec: int = 60

    # ── Upload safety (spec §6.4) ───────────────────────────────────────────
    # Byte-size guard (prevents a runaway upload filling the disk).
    max_upload_mb: int = 50
    # Optional row ceiling. ``0`` (default) means no row cap — study scale is
    # guidance, not a gate. A public-facing instance can set a small ceiling
    # (e.g. MAX_UPLOAD_ROWS=2000) to keep it a demo, not a bulk service.
    max_upload_rows: int = 0

    # ── Data retention (spec §6.8) ──────────────────────────────────────────
    retention_uploads_days: int = 90
    retention_exports_days: int = 30
    retention_revoked_sessions_days: int = 90

    # ── Observability ───────────────────────────────────────────────────────
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    sentry_dsn: str | None = None

    # ── Federation-lite (G1) ────────────────────────────────────────────────
    # This instance's identity + Ed25519 signing key (32-byte private seed,
    # hex-encoded). When unset, a dev key is derived from the instance id so
    # local round-trips work; production sets a real key and documents rotation.
    federation_instance_id: str = "local-instance"
    federation_private_key: str | None = None  # hex Ed25519 seed (64 hex chars)
    # Trusted peers: comma-separated ``instance_id:hex_public_key`` pairs whose
    # signed exports this instance will accept on import.
    federation_trusted_keys: str = ""

    # ── Validators (fail-fast) ──────────────────────────────────────────────
    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_strength(cls, v: str, info) -> str:
        # Only enforce when JWT auth is actually in use.
        mode = info.data.get("auth_mode", "jwt")
        if mode == "jwt":
            if v == _PLACEHOLDER_JWT_SECRET:
                raise ValueError(
                    "JWT_SECRET is still the shipped default — set a strong random value "
                    "(e.g. `python -c \"import secrets;print(secrets.token_urlsafe(48))\"`)."
                )
            if len(v.encode("utf-8")) < 32:
                raise ValueError("JWT_SECRET must be at least 32 bytes when AUTH_MODE=jwt")
        return v

    @model_validator(mode="after")
    def _auto_secure_cookie(self):
        # An HTTPS deployment must send the refresh cookie as Secure; enable it
        # automatically so a prod instance can't accidentally leak it over the
        # wire because COOKIE_SECURE was forgotten.
        if self.app_base_url.lower().startswith("https://") and not self.cookie_secure:
            object.__setattr__(self, "cookie_secure", True)
        return self

    @field_validator("llm_threshold")
    @classmethod
    def _threshold_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("LLM_THRESHOLD must be between 0.0 and 1.0")
        return v

    # ── Derived helpers ─────────────────────────────────────────────────────
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_email_domain_list(self) -> list[str]:
        return [d.strip().lower().lstrip("@") for d in self.allowed_email_domains.split(",") if d.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings instance (constructed once per process)."""
    return Settings()


settings = get_settings()
