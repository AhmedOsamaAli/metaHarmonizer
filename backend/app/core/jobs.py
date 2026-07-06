"""Redis-backed job bus: progress broadcast, cancellation, and WS tickets.

All state lives in Redis (never in-process) so it works across many concurrent
jobs and multiple API/worker instances. Redis ops here are best-effort — a blip
logs at debug and must never fail the job itself.
"""

from __future__ import annotations

import json
import logging
import secrets
from typing import Any

from app.core.redis import get_redis
from app.core.settings import settings

logger = logging.getLogger(__name__)


# ── channel / key helpers ─────────────────────────────────────────────────────
def job_channel(study_id: str) -> str:
    return f"ws:jobs:{study_id}"


def _snapshot_key(study_id: str) -> str:
    return f"job:snapshot:{study_id}"


def _cancel_key(study_id: str) -> str:
    return f"job:cancel:{study_id}"


def user_channel(user_id: int) -> str:
    return f"ws:notify:{user_id}"


# ── progress publish / snapshot ───────────────────────────────────────────────
async def publish_progress(study_id: str, payload: dict[str, Any]) -> None:
    """Broadcast a progress event and cache it as the latest snapshot (1h TTL)."""
    payload = {"study_id": study_id, **payload}
    body = json.dumps(payload)
    try:
        r = get_redis()
        await r.publish(job_channel(study_id), body)
        await r.set(_snapshot_key(study_id), body, ex=3600)
    except Exception:
        # Best-effort: a Redis blip must never fail the job itself.
        logger.debug("publish_progress failed for %s", study_id, exc_info=True)


async def get_snapshot(study_id: str) -> dict[str, Any] | None:
    try:
        raw = await get_redis().get(_snapshot_key(study_id))
        return json.loads(raw) if raw else None
    except Exception:
        logger.debug("get_snapshot failed for %s", study_id, exc_info=True)
        return None


async def notify_user(user_id: int, payload: dict[str, Any]) -> None:
    try:
        await get_redis().publish(user_channel(user_id), json.dumps(payload))
    except Exception:
        logger.debug("notify_user failed for %s", user_id, exc_info=True)


# ── cancellation ──────────────────────────────────────────────────────────────
async def request_cancel(study_id: str) -> None:
    try:
        await get_redis().set(_cancel_key(study_id), "1", ex=3600)
    except Exception:
        logger.debug("request_cancel failed for %s", study_id, exc_info=True)


async def is_cancelled(study_id: str) -> bool:
    try:
        return bool(await get_redis().get(_cancel_key(study_id)))
    except Exception:
        logger.debug("is_cancelled failed for %s", study_id, exc_info=True)
        return False


async def clear_cancel(study_id: str) -> None:
    try:
        await get_redis().delete(_cancel_key(study_id))
    except Exception:
        logger.debug("clear_cancel failed for %s", study_id, exc_info=True)


# ── WS auth tickets (one-time, short-lived) ───────────────────────────────────
async def mint_ws_ticket(user_id: int) -> str:
    ticket = secrets.token_urlsafe(32)
    await get_redis().set(f"ws:ticket:{ticket}", str(user_id), ex=settings.ws_ticket_ttl_sec)
    return ticket


async def redeem_ws_ticket(ticket: str) -> int | None:
    """Validate + consume a ticket. Returns the user id, or None if invalid."""
    try:
        r = get_redis()
        key = f"ws:ticket:{ticket}"
        uid = await r.get(key)
        if uid is None:
            return None
        await r.delete(key)  # one-time use
        return int(uid)
    except Exception:
        return None


class JobCancelled(Exception):
    """Raised inside the task when a cancel flag is observed at a stage boundary."""
