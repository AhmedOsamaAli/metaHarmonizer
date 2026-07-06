"""
Cross-cutting HTTP middleware and exception handlers.

- RequestIdMiddleware: assigns/propagates a request id (honours an inbound
  ``X-Request-ID``), stores it in the logging contextvar, and echoes it on the
  response header.
- Exception handlers: every error response uses the unified envelope
  (spec §6.1) and includes the request id, so a user-visible failure is one
  grep away from its logs.

Registered in app/main.py via ``install_observability``.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.errors import AppError, error_envelope
from app.core.logging import request_id_ctx

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get(REQUEST_ID_HEADER) or f"req_{uuid.uuid4().hex}"
        token = request_id_ctx.set(rid)
        request.state.request_id = rid
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers[REQUEST_ID_HEADER] = rid
        return response


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "") or request_id_ctx.get()


async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    headers = {}
    if getattr(exc, "retry_after", None):
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope(exc.code, exc.message, details=exc.details, request_id=_rid(request)),
        headers=headers,
    )


async def _db_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    # Postgres blip / connection loss -> degrade to 503 (retryable) instead of a
    # bare 500, so a brief outage doesn't look like an app crash.
    return JSONResponse(
        status_code=503,
        content=error_envelope(
            "DATABASE_UNAVAILABLE",
            "The database is temporarily unavailable. Please retry shortly.",
            request_id=_rid(request),
        ),
        headers={"Retry-After": "5"},
    )


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope("HTTP_ERROR", str(exc.detail), request_id=_rid(request)),
    )


async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_envelope(
            "VALIDATION_ERROR",
            "Request validation failed.",
            details={"errors": exc.errors()},
            request_id=_rid(request),
        ),
    )


async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=error_envelope("INTERNAL_ERROR", "Internal server error.", request_id=_rid(request)),
    )


def install_observability(app: FastAPI) -> None:
    """Attach request-id middleware + unified error handlers."""
    from sqlalchemy.exc import InterfaceError, OperationalError

    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(OperationalError, _db_unavailable_handler)
    app.add_exception_handler(InterfaceError, _db_unavailable_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(Exception, _unhandled_handler)
