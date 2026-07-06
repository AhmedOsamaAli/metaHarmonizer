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


def test_service_unavailable_error_shape():
    err = ServiceUnavailableError("busy")
    assert err.status_code == 503
    assert err.code == "SERVICE_UNAVAILABLE"
    assert err.retry_after == 30
