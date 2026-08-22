"""Operational-contract tests: error envelope, request-id, pagination (spec §6.1)."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.errors import ConflictError
from app.core.middleware import REQUEST_ID_HEADER, install_observability
from app.core.pagination import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    build_page,
    clamp_limit,
    decode_cursor,
    encode_cursor,
)


def _app() -> FastAPI:
    app = FastAPI()
    install_observability(app)

    @app.get("/ok")
    async def ok():
        return {"ok": True}

    @app.get("/boom-app")
    async def boom_app():
        raise ConflictError("stale", details={"current_version": 7})

    @app.get("/boom-unhandled")
    async def boom_unhandled():
        raise RuntimeError("kaboom")

    @app.get("/boom-http")
    async def boom_http():
        raise HTTPException(429, "slow down", headers={"Retry-After": "30"})

    return app


def test_request_id_generated_and_echoed():
    client = TestClient(_app())
    r = client.get("/ok")
    assert r.status_code == 200
    assert r.headers[REQUEST_ID_HEADER].startswith("req_")


def test_inbound_request_id_is_honoured():
    client = TestClient(_app())
    r = client.get("/ok", headers={REQUEST_ID_HEADER: "req_custom123"})
    assert r.headers[REQUEST_ID_HEADER] == "req_custom123"


def test_app_error_uses_envelope_with_request_id():
    client = TestClient(_app(), raise_server_exceptions=False)
    r = client.get("/boom-app")
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "MAPPING_CONFLICT"
    assert body["error"]["details"]["current_version"] == 7
    assert body["error"]["request_id"] == r.headers[REQUEST_ID_HEADER]


def test_http_exception_preserves_headers():
    client = TestClient(_app())
    r = client.get("/boom-http")
    assert r.status_code == 429
    assert r.headers["Retry-After"] == "30"


def test_unhandled_error_is_enveloped_not_leaked():
    client = TestClient(_app(), raise_server_exceptions=False)
    r = client.get("/boom-unhandled")
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "kaboom" not in body["error"]["message"]  # no internal detail leaked


# ── pagination ───────────────────────────────────────────────────────────────
def test_clamp_limit_bounds():
    assert clamp_limit(None) == DEFAULT_LIMIT
    assert clamp_limit(0) == DEFAULT_LIMIT
    assert clamp_limit(10) == 10
    assert clamp_limit(99999) == MAX_LIMIT


def test_cursor_roundtrip():
    assert decode_cursor(encode_cursor({"id": 42})) == {"id": 42}
    assert decode_cursor(None) is None
    assert decode_cursor("not-base64!!") is None


def test_build_page_sets_next_cursor_when_more():
    rows = [{"id": i} for i in range(1, 7)]  # 6 rows, limit 5 -> has more
    page = build_page(rows, limit=5, cursor_of=lambda r: r["id"])
    assert len(page.items) == 5
    assert decode_cursor(page.next_cursor) == 5


def test_build_page_no_cursor_when_exhausted():
    rows = [{"id": 1}, {"id": 2}]
    page = build_page(rows, limit=5, cursor_of=lambda r: r["id"])
    assert page.next_cursor is None
