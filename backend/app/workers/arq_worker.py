"""
arq worker (Sprint 4, ``JOB_MODE=queue``).

Run with::

    cd backend
    arq app.workers.arq_worker.WorkerSettings

Each worker process pre-warms the engine once on startup and then processes one
job at a time; scale concurrency by running more worker processes/containers.
Retries (3 attempts, backoff) and the hard timeout are enforced by arq here, so
a stuck job is killed and a transient failure is retried.
"""

from __future__ import annotations

import logging

from arq import Retry, cron
from arq.connections import RedisSettings

from app.core.settings import settings
from app.workers.retention import run_retention
from app.workers.tasks import (
    RetryableJobError,
    nightly_labeled_export,
    retry_delay_sec,
    run_harmonize,
)

logger = logging.getLogger("app.worker")


async def harmonize_job(ctx, **kwargs) -> None:
    """arq entry point — delegates to the shared task implementation."""
    try:
        await run_harmonize(**kwargs)
    except RetryableJobError as exc:
        raise Retry(defer=retry_delay_sec(exc.attempt)) from exc


async def nightly_labeled_export_job(ctx) -> None:
    """Cron entry point — persist the global labeled dataset (G9/U16)."""
    await nightly_labeled_export()


async def retention_job(ctx) -> None:
    """Cron entry point — nightly data-retention purge (§6.8)."""
    counts = await run_retention()
    logger.info("retention purge: %s", counts)


async def _startup(ctx) -> None:
    # Load the engine + dictionaries once so the first job isn't cold.
    try:
        from app.engine_adapter import get_engine

        get_engine().pre_warm()
    except Exception:  # noqa: BLE001
        logger.warning("engine pre-warm skipped", exc_info=True)


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [harmonize_job]
    cron_jobs = [
        # Nightly labeled-dataset dump (G9/U16), 02:30 server time.
        cron(nightly_labeled_export_job, hour=2, minute=30, run_at_startup=False),
        # Nightly data-retention purge (§6.8), 03:30 server time.
        cron(retention_job, hour=3, minute=30, run_at_startup=False),
    ]
    on_startup = _startup
    max_jobs = settings.worker_max_jobs
    job_timeout = settings.job_hard_timeout_sec
    max_tries = settings.job_max_attempts
    retry_jobs = True
