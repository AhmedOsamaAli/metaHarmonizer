"""
Sentry initialisation — opt-in, no-op by default.

Calling ``init_sentry()`` does nothing unless ``SENTRY_DSN`` is set, so local
dev and CI stay quiet. The ``sentry-sdk`` package is an optional dependency:
if it isn't installed, init is skipped with a debug log rather than failing.
Release is tagged with the git short SHA when available.
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

from app.core.settings import settings

logger = logging.getLogger("app.sentry")

_FILTERED = "[Filtered]"
_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "cookies",
    "email",
    "file_name",
    "filename",
    "medical_record_number",
    "mrn",
    "password",
    "patient_id",
    "raw_value",
    "recipient",
    "sample_id",
    "secret",
    "set_cookie",
    "subject_id",
    "token",
    "upload_name",
    "user_email",
}
_SENSITIVE_SUFFIXES = ("_api_key", "_password", "_secret", "_token")


def _normalise_key(key: object) -> str:
    return str(key).strip().lower().replace("-", "_").replace(" ", "_")


def _is_sensitive_key(key: object) -> bool:
    normalised = _normalise_key(key)
    return normalised in _SENSITIVE_KEYS or normalised.endswith(_SENSITIVE_SUFFIXES)


def _scrub_value(value: Any, path: tuple[str, ...] = ()) -> Any:
    if path and path[-1] == "data" and "request" in path:
        return _FILTERED
    if path and path[-1] in {"formatted", "message"}:
        return _FILTERED
    if len(path) >= 3 and path[-1] == "value" and "exception" in path:
        return _FILTERED

    if isinstance(value, dict):
        return {
            key: (
                _FILTERED
                if _is_sensitive_key(key) and not (_normalise_key(key) == "filename" and "stacktrace" in path)
                else _scrub_value(item, path + (_normalise_key(key),))
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub_value(item, path) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub_value(item, path) for item in value)
    return value


def scrub_sentry_event(event: dict[str, Any], _hint: dict[str, Any] | None = None) -> dict[str, Any]:
    """Remove credentials and user-supplied metadata before Sentry transport."""
    return _scrub_value(event)


def _git_short_sha() -> str | None:
    sha = os.getenv("GIT_SHA")
    if sha:
        return sha[:12]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def init_sentry() -> bool:
    """Initialise Sentry if configured. Returns True when actually enabled."""
    if not settings.sentry_dsn:
        logger.debug("Sentry disabled (SENTRY_DSN unset).")
        return False
    try:
        import sentry_sdk  # type: ignore
    except ImportError:
        logger.warning("SENTRY_DSN set but sentry-sdk is not installed; skipping.")
        return False

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        release=_git_short_sha(),
        traces_sample_rate=0.0,  # errors only by default; tracing opt-in later
        send_default_pii=False,
        before_send=scrub_sentry_event,
    )
    logger.info("Sentry initialised.")
    return True
