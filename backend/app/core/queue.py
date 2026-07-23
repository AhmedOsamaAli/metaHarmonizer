"""
Job dispatch (Sprint 4) — inline executor vs arq queue.

``enqueue_harmonize`` is the one entry point routers call. In ``inline`` mode it
runs the task in a background asyncio task within the API process (the heavy
engine work is offloaded to a thread inside the task, so the event loop stays
free for other users). In ``queue`` mode it pushes the job to an arq worker pool
for true horizontal scale across many concurrent jobs.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.settings import settings
from app.workers.tasks import run_harmonize

logger = logging.getLogger("app.queue")

# Keep strong refs to inline tasks so they aren't garbage-collected mid-run.
_inline_tasks: set[asyncio.Task] = set()

_arq_pool = None


async def has_capacity() -> bool:
    """Backpressure gate: True if a new harmonize job can be accepted now.

    Queue mode: reject when the pending arq queue is deeper than
    ``job_max_queue_depth`` (fail-open on a Redis hiccup so a blip can't wedge
    uploads). Inline mode: cap concurrent in-process jobs at ``max_inline_jobs``.
    """
    if settings.job_mode == "queue":
        try:
            pool = await _get_arq_pool()
            depth = await pool.zcard("arq:queue")
        except Exception:
            return True
        return depth < settings.job_max_queue_depth
    return len(_inline_tasks) < settings.max_inline_jobs


async def _get_arq_pool():
    global _arq_pool
    if _arq_pool is None:
        from arq import create_pool
        from arq.connections import RedisSettings

        _arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _arq_pool


async def enqueue_harmonize(
    *,
    job_id: int,
    study_id: str,
    file_path: str,
    suffix: str,
    curated_path: str,
    owner_id: int | None,
    mode: str = "both",
    ontology_columns: list[str] | None = None,
    target_schema: str | None = None,
) -> None:
    kwargs = dict(
        job_id=job_id,
        study_id=study_id,
        file_path=file_path,
        suffix=suffix,
        curated_path=curated_path,
        owner_id=owner_id,
        mode=mode,
        ontology_columns=ontology_columns,
        target_schema=target_schema,
    )

    if settings.job_mode == "queue":
        # Never fall back to inline execution in queue mode: running the engine
        # in the API process would defeat backpressure and can OOM the API tier.
        # If the queue is unreachable, let the error propagate so the caller
        # sheds load with a 503 instead.
        pool = await _get_arq_pool()
        await pool.enqueue_job("harmonize_job", **kwargs)
        return

    # Inline: background task in this process (engine work is threaded inside).
    task = asyncio.create_task(run_harmonize(**kwargs))
    _inline_tasks.add(task)
    task.add_done_callback(_inline_tasks.discard)
