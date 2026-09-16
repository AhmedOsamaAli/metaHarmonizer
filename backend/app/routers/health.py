"""Health endpoints — liveness (/healthz) and readiness (/readyz) probes.

/readyz returns 200 only when every configured dependency (Postgres, Redis) is
reachable, else 503 with a per-dependency status map. Unconfigured checks report
"skipped" rather than failing readiness.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Response, status

from app.core.deps import require_role
from app.core.metrics import render_metrics

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness: the process is up and serving. No dependency checks."""
    return {"status": "ok"}


async def _check_postgres() -> tuple[bool, str]:
    """Best-effort Postgres ping. 'skipped' until DATABASE_URL is set (Sprint 2)."""
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        return True, "skipped"
    try:
        import asyncpg  # type: ignore

        # asyncpg wants the plain postgres:// form, not the +asyncpg driver suffix.
        conn = await asyncpg.connect(dsn.replace("+asyncpg", ""), timeout=3)
        try:
            await conn.execute("SELECT 1")
        finally:
            await conn.close()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001 — readiness must never raise
        return False, f"error: {type(exc).__name__}"


async def _check_redis() -> tuple[bool, str]:
    """Best-effort Redis ping. 'skipped' until REDIS_URL is set (Sprint 4)."""
    url = os.getenv("REDIS_URL")
    if not url:
        return True, "skipped"
    try:
        import redis.asyncio as redis  # type: ignore

        client = redis.from_url(url, socket_connect_timeout=3)
        try:
            await client.ping()
        finally:
            await client.aclose()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"error: {type(exc).__name__}"


def _check_ontology_kb() -> tuple[bool, str]:
    from app.engine_adapter._ontology import runtime_asset_issues
    from app.engine_adapter.kb_assets import runtime_engine_required

    if not runtime_engine_required():
        return True, "disabled"
    issues = runtime_asset_issues()
    if issues:
        return False, f"error: incomplete ({len(issues)} required asset(s) missing)"
    return True, "ok"


@router.get("/readyz")
async def readyz(response: Response) -> dict[str, object]:
    """Readiness: every configured dependency is reachable."""
    pg_ok, pg_msg = await _check_postgres()
    redis_ok, redis_msg = await _check_redis()
    kb_ok, kb_msg = _check_ontology_kb()

    checks = {"postgres": pg_msg, "redis": redis_msg, "ontology_kb": kb_msg}
    ready = pg_ok and redis_ok and kb_ok
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"ready": ready, "checks": checks}


@router.get("/metrics", include_in_schema=False)
async def metrics(_admin=Depends(require_role("admin"))) -> Response:
    """Prometheus exposition (admin-scoped) — golden signals + auth failures."""
    return render_metrics()
