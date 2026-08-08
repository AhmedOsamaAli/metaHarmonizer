"""
job_runs lifecycle (Sprint 4, spec §6.3).

State machine: queued -> running -> {succeeded | failed | cancelled}.
On terminal failure after retries, a row is also written to ``job_failures``
(dead-letter) for the admin re-queue/discard surface.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JobFailure, JobRun


async def create_job(db: AsyncSession, *, study_id: str, kind: str) -> JobRun:
    job = JobRun(study_id=study_id, kind=kind, state="queued", attempt=0)
    db.add(job)
    await db.flush()
    return job


async def get_job(db: AsyncSession, job_id: int) -> JobRun | None:
    return await db.get(JobRun, job_id)


async def latest_for_study(db: AsyncSession, study_id: str) -> JobRun | None:
    stmt = (
        select(JobRun)
        .where(JobRun.study_id == study_id)
        .order_by(JobRun.created_at.desc())
        .limit(1)
    )
    return await db.scalar(stmt)


async def mark_running(db: AsyncSession, job: JobRun) -> None:
    job.state = "running"
    job.attempt += 1
    job.started_at = datetime.now(timezone.utc)
    await db.flush()


async def mark_retrying(
    db: AsyncSession,
    job: JobRun,
    *,
    error_code: str,
    error_message: str,
) -> None:
    job.state = "queued"
    job.error_code = error_code
    job.error_message = error_message[:2000]
    job.finished_at = None
    await db.flush()


async def mark_succeeded(db: AsyncSession, job: JobRun) -> None:
    job.state = "succeeded"
    job.finished_at = datetime.now(timezone.utc)
    await db.flush()


async def mark_cancelled(db: AsyncSession, job: JobRun) -> None:
    job.state = "cancelled"
    job.finished_at = datetime.now(timezone.utc)
    await db.flush()


async def mark_failed(
    db: AsyncSession,
    job: JobRun,
    *,
    error_code: str,
    error_message: str,
    dead_letter: bool = False,
) -> None:
    job.state = "failed"
    job.error_code = error_code
    job.error_message = error_message[:2000]
    job.finished_at = datetime.now(timezone.utc)
    if dead_letter:
        db.add(
            JobFailure(
                job_run_id=job.id,
                study_id=job.study_id,
                kind=job.kind,
                error_code=error_code,
                error_message=error_message[:2000],
                attempts=job.attempt,
            )
        )
    await db.flush()
