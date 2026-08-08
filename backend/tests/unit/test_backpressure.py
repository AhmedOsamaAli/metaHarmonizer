"""Backpressure gate: has_capacity() in inline mode."""

from __future__ import annotations

import pytest

from app.core import queue as q
from app.core.errors import ServiceUnavailableError


@pytest.mark.asyncio
async def test_inline_capacity_respects_cap(monkeypatch):
    monkeypatch.setattr(q.settings, "job_mode", "inline", raising=False)
    monkeypatch.setattr(q.settings, "max_inline_jobs", 8, raising=False)
    assert await q.has_capacity() is True

    monkeypatch.setattr(q.settings, "max_inline_jobs", 0, raising=False)
    assert await q.has_capacity() is False


@pytest.mark.asyncio
async def test_inline_retries_use_approved_backoff(monkeypatch):
    from app.workers.tasks import RetryableJobError

    attempts = 0
    delays: list[int] = []

    async def run(**_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RetryableJobError("transient", attempt=attempts)

    async def sleep(delay: int):
        delays.append(delay)

    monkeypatch.setattr(q, "run_harmonize", run)
    monkeypatch.setattr(q.asyncio, "sleep", sleep)
    monkeypatch.setattr(q.settings, "job_max_attempts", 3, raising=False)
    monkeypatch.setattr(q.settings, "job_retry_delay_sec", 30, raising=False)

    await q._run_inline_with_retries({})

    assert attempts == 3
    assert delays == [30, 60]


def test_service_unavailable_error_shape():
    err = ServiceUnavailableError("busy")
    assert err.status_code == 503
    assert err.code == "SERVICE_UNAVAILABLE"
    assert err.retry_after == 30
