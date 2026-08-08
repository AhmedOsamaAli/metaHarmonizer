"""Sentry init is a safe no-op unless configured."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import app.core.settings as settings_mod
from app.core.sentry import init_sentry, scrub_sentry_event


def test_init_sentry_noop_without_dsn(monkeypatch):
    # Default settings have no DSN -> init returns False, no exception.
    monkeypatch.setattr(settings_mod.settings, "sentry_dsn", None, raising=False)
    assert init_sentry() is False


def test_init_sentry_registers_scrubber(monkeypatch):
    captured = {}
    fake_sdk = SimpleNamespace(init=lambda **kwargs: captured.update(kwargs))
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sdk)
    monkeypatch.setattr(settings_mod.settings, "sentry_dsn", "https://public@example.test/1", raising=False)

    assert init_sentry() is True
    assert captured["before_send"] is scrub_sentry_event
    assert captured["send_default_pii"] is False


def test_scrubber_removes_sensitive_metadata_and_keeps_operations_context():
    event = {
        "request": {
            "method": "POST",
            "url": "https://example.test/api/v1/harmonize",
            "headers": {
                "Authorization": "Bearer private-token",
                "User-Agent": "test-client",
            },
            "data": {
                "filename": "patient_metadata.csv",
                "email": "curator@example.org",
                "patient_id": "PATIENT-123",
                "raw_value": "Glioblastoma",
            },
        },
        "contexts": {
            "job": {
                "study_id": "study-42",
                "sample_id": "SAMPLE-7",
                "nested_api_key": "secret-key",
                "attempt": 2,
            }
        },
        "tags": {"component": "worker"},
    }

    scrubbed = scrub_sentry_event(event)

    assert scrubbed["request"]["headers"]["Authorization"] == "[Filtered]"
    assert scrubbed["request"]["headers"]["User-Agent"] == "test-client"
    assert scrubbed["request"]["data"] == "[Filtered]"
    assert scrubbed["contexts"]["job"]["sample_id"] == "[Filtered]"
    assert scrubbed["contexts"]["job"]["nested_api_key"] == "[Filtered]"
    assert scrubbed["contexts"]["job"]["study_id"] == "study-42"
    assert scrubbed["contexts"]["job"]["attempt"] == 2
    assert scrubbed["tags"]["component"] == "worker"


def test_scrubber_filters_free_form_messages_but_preserves_stack_details():
    event = {
        "message": "Failed to parse patient_metadata.csv for curator@example.org",
        "exception": {
            "values": [
                {
                    "type": "ValueError",
                    "value": "Invalid patient PATIENT-123 value Glioblastoma",
                    "stacktrace": {
                        "frames": [{"filename": "app/workers/tasks.py", "lineno": 42}]
                    },
                }
            ]
        },
        "breadcrumbs": [{"message": "uploaded patient_metadata.csv", "category": "job"}],
    }

    scrubbed = scrub_sentry_event(event)

    assert scrubbed["message"] == "[Filtered]"
    assert scrubbed["exception"]["values"][0]["value"] == "[Filtered]"
    assert scrubbed["exception"]["values"][0]["type"] == "ValueError"
    assert scrubbed["exception"]["values"][0]["stacktrace"]["frames"][0]["filename"] == "app/workers/tasks.py"
    assert scrubbed["exception"]["values"][0]["stacktrace"]["frames"][0]["lineno"] == 42
    assert scrubbed["breadcrumbs"][0]["message"] == "[Filtered]"
