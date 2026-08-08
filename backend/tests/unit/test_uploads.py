"""Upload byte-size guard tests (spec §6.4). No row/column ceilings exist."""

from __future__ import annotations

import pytest

from app.core.uploads import PayloadTooLargeError, check_upload_size
from app.workers import tasks


def test_upload_size_within_limit_ok():
    check_upload_size(5 * 1024 * 1024, max_mb=50)  # no raise


def test_upload_size_over_limit_raises_413():
    with pytest.raises(PayloadTooLargeError) as ei:
        check_upload_size(60 * 1024 * 1024, max_mb=50)
    assert ei.value.status_code == 413
    assert ei.value.details["limit_bytes"] == 50 * 1024 * 1024


def test_worker_rejects_oversized_stored_upload(tmp_path, monkeypatch):
    upload = tmp_path / "large.csv"
    upload.write_text("column\nvalue\n", encoding="utf-8")
    monkeypatch.setattr(tasks.settings, "max_upload_mb", 0, raising=False)

    with pytest.raises(tasks.PermanentJobError, match="exceeding"):
        tasks._run_pipeline("s1", str(upload), ".csv", str(upload))


def test_worker_rejects_excess_rows(tmp_path, monkeypatch):
    upload = tmp_path / "rows.csv"
    upload.write_text("column\none\ntwo\n", encoding="utf-8")
    monkeypatch.setattr(tasks.settings, "max_upload_mb", 50, raising=False)
    monkeypatch.setattr(tasks.settings, "max_upload_rows", 1, raising=False)

    with pytest.raises(tasks.PermanentJobError, match="2 rows"):
        tasks._run_pipeline("s1", str(upload), ".csv", str(upload))


def test_retry_delay_is_exponential(monkeypatch):
    monkeypatch.setattr(tasks.settings, "job_retry_delay_sec", 30, raising=False)

    assert tasks.retry_delay_sec(1) == 30
    assert tasks.retry_delay_sec(2) == 60
