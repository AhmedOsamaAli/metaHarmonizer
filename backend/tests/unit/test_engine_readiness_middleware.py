from __future__ import annotations

import asyncio

from app.core.middleware import EngineReadinessMiddleware
from app.engine_adapter import _ontology


def test_unready_engine_rejects_before_receiving_body(monkeypatch) -> None:
    monkeypatch.setattr(_ontology, "runtime_asset_error", lambda: "KB not ready")
    received = False
    downstream_called = False
    sent: list[dict] = []

    async def downstream(_scope, _receive, _send):
        nonlocal downstream_called
        downstream_called = True

    async def receive():
        nonlocal received
        received = True
        return {"type": "http.request", "body": b"upload", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/harmonize",
        "headers": [],
    }
    asyncio.run(EngineReadinessMiddleware(downstream)(scope, receive, send))

    assert not received
    assert not downstream_called
    assert sent[0]["status"] == 503
    headers = dict(sent[0]["headers"])
    assert headers[b"retry-after"] == b"30"
    assert headers[b"x-request-id"].startswith(b"req_")
    assert headers[b"x-content-type-options"] == b"nosniff"


def test_ready_engine_passes_request_to_application(monkeypatch) -> None:
    monkeypatch.setattr(_ontology, "runtime_asset_error", lambda: None)
    downstream_called = False

    async def downstream(_scope, _receive, _send):
        nonlocal downstream_called
        downstream_called = True

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/harmonize",
        "headers": [],
    }
    asyncio.run(
        EngineReadinessMiddleware(downstream)(
            scope,
            lambda: None,
            lambda _message: None,
        )
    )

    assert downstream_called
