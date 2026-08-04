"""
WebSocket endpoints (Sprint 4) — live job progress + per-user notifications.

Auth: browsers can't send an ``Authorization`` header on a WebSocket, so the
client first calls ``POST /api/v1/ws/ticket`` (Bearer-authed) to get a one-time,
30-second nonce, then connects with ``?ticket=...``. The socket relays messages
from the Redis pub/sub bus, so progress produced by *any* worker reaches the
user — correct under many concurrent users and horizontally-scaled instances.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user, ensure_study_visible, require_role
from app.core.jobs import (
    get_snapshot,
    job_channel,
    mint_ws_ticket,
    redeem_ws_ticket,
    request_cancel,
    user_channel,
)
from app.core.metrics import WS_CONNECTIONS
from app.core.redis import get_redis
from app.db.models import User
from app.db.session import get_db
from app.repositories import jobs as jobs_repo
from app.repositories import studies as studies_repo

logger = logging.getLogger("app.ws")

router = APIRouter(prefix="/api/v1", tags=["ws"])


@router.post("/ws/ticket")
async def create_ws_ticket(user: User = Depends(current_user)) -> dict[str, object]:
    """Mint a one-time, short-lived ticket for authenticating a WebSocket."""
    ticket = await mint_ws_ticket(user.id)
    return {"ticket": ticket}


@router.get("/jobs/{study_id}")
async def job_status(
    study_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Poll fallback: latest job state for a study (for clients without WS)."""
    ensure_study_visible(await studies_repo.get_study(db, study_id), user)
    job = await jobs_repo.latest_for_study(db, study_id)
    snapshot = await get_snapshot(study_id)
    return {
        "study_id": study_id,
        "state": job.state if job else None,
        "attempt": job.attempt if job else 0,
        "error_code": job.error_code if job else None,
        "progress": snapshot,
    }


@router.post("/jobs/{study_id}/cancel", status_code=202)
async def cancel_job(
    study_id: str,
    user: User = Depends(require_role("curator")),
) -> dict[str, object]:
    """Request cancellation of a running harmonize job (HTTP equivalent of the
    WebSocket ``cancel`` action, for clients that poll rather than hold a WS).

    Sets the Redis cancel flag the worker polls at each stage boundary; the
    terminal ``cancelled`` state is then broadcast on the bus as usual.
    """
    await request_cancel(study_id)
    return {"study_id": study_id, "cancel_requested": True}


async def _relay_channel(ws: WebSocket, channel: str) -> None:
    """Forward Redis pub/sub messages on ``channel`` to the WebSocket client,
    after first sending the cached snapshot (so late joiners see current state)."""
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message is None or message.get("type") != "message":
                continue
            data = message["data"]
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            await ws.send_text(data)
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()


async def _read_client(ws: WebSocket, study_id: str | None) -> None:
    """Handle client -> server messages (currently: cancel a running job)."""
    while True:
        raw = await ws.receive_text()
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if study_id and msg.get("action") == "cancel":
            await request_cancel(study_id)


@router.websocket("/ws/jobs/{study_id}")
async def ws_jobs(websocket: WebSocket, study_id: str) -> None:
    """Live progress for one study's harmonize job."""
    ticket = websocket.query_params.get("ticket", "")
    user_id = await redeem_ws_ticket(ticket)
    if user_id is None:
        await websocket.close(code=4401)  # unauthorized
        return

    await websocket.accept()
    WS_CONNECTIONS.inc()

    # Push the current snapshot immediately on connect.
    snapshot = await get_snapshot(study_id)
    if snapshot:
        await websocket.send_text(json.dumps(snapshot))

    relay = asyncio.create_task(_relay_channel(websocket, job_channel(study_id)))
    reader = asyncio.create_task(_read_client(websocket, study_id))
    try:
        await asyncio.wait({relay, reader}, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        for t in (relay, reader):
            t.cancel()
        WS_CONNECTIONS.dec()


@router.websocket("/ws/notify/{user_id}")
async def ws_notify(websocket: WebSocket, user_id: int) -> None:
    """Per-user notification stream (e.g. job-complete bell)."""
    ticket = websocket.query_params.get("ticket", "")
    authed = await redeem_ws_ticket(ticket)
    if authed is None or authed != user_id:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    WS_CONNECTIONS.inc()
    relay = asyncio.create_task(_relay_channel(websocket, user_channel(user_id)))
    reader = asyncio.create_task(_read_client(websocket, None))
    try:
        await asyncio.wait({relay, reader}, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        for t in (relay, reader):
            t.cancel()
        WS_CONNECTIONS.dec()
