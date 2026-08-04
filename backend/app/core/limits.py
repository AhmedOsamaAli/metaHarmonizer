"""
Idempotency + rate-limit middleware (spec §6.1, §6.4).

IdempotencyMiddleware
  Mutating routes that a curator might retry (POST /studies, /harmonize,
  /federation/import) accept an ``Idempotency-Key`` header. The first response
  is cached in Redis for 24h keyed by (route, key); a retry replays the cached
  response instead of re-running the work.

RateLimitMiddleware
  Sliding-window limiter backed by a Redis sorted set. Authenticated callers get
  a higher budget than anonymous ones. On limit, returns 429 with ``Retry-After``
  and the unified error envelope.

Availability note: if Redis is unreachable, both middlewares **fail open**
(allow the request, log a warning) so a cache blip degrades one feature rather
than taking the app down. The spec's stricter "fail closed" stance can be
enabled later via settings if required.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.errors import error_envelope
from app.core.redis import get_redis
from app.core.security import API_TOKEN_PREFIX, decode_token, hash_api_token
from app.core.settings import settings

logger = logging.getLogger("app.ratelimit")
IDEMPOTENCY_HEADER = "Idempotency-Key"
IDEMPOTENT_ROUTES = ("/studies", "/harmonize", "/federation/import")
IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60

# Paths exempt from rate limiting. These are authenticated, high-frequency, and
# not unauthenticated brute-force vectors:
#   - /auth/refresh fires on every page load and is gated by a valid refresh
#     cookie; counting it would log legitimate users out on reload.
#   - /jobs/ is polled while a study is processing (live progress fallback).
#   - /ws/ticket is requested to open each live-progress WebSocket.
# Login/register stay limited.
RATE_LIMIT_EXEMPT_PREFIXES = (
    "/api/v1/auth/refresh",
    "/api/v1/jobs/",
    "/api/v1/ws/ticket",
)


async def _client_id(request: Request) -> tuple[str, bool]:
    """Return (identity, is_authenticated). User id when available, else IP."""
    user = getattr(request.state, "user_id", None)
    if user:
        return f"user:{user}", True

    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        if token.startswith(API_TOKEN_PREFIX):
            from app.db.session import SessionLocal
            from app.repositories import api_tokens as api_tokens_repo

            async with SessionLocal() as db:
                record = await api_tokens_repo.get_active_by_hash(db, hash_api_token(token))
            if record is not None:
                return f"user:{record.user_id}", True
        else:
            try:
                payload = decode_token(token)
                if payload.get("type") == "access" and payload.get("sub"):
                    return f"user:{int(payload['sub'])}", True
            except (jwt.PyJWTError, TypeError, ValueError):
                pass

    if settings.auth_mode == "none":
        ip = request.client.host if request.client else "unknown"
        return f"dev:{ip}", True
    ip = request.client.host if request.client else "unknown"
    return f"ip:{ip}", False


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(RATE_LIMIT_EXEMPT_PREFIXES):
            return await call_next(request)

        identity, is_auth = await _client_id(request)
        window = settings.rate_limit_window_sec
        limit = settings.rate_limit_auth if is_auth else settings.rate_limit_anon
        now = time.time()
        key = f"ratelimit:{identity}"

        try:
            r = get_redis()
            async with r.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(key, 0, now - window)
                # Member must be globally unique per request. Using id(request)
                # is unsafe: CPython reuses the address of a freed Request across
                # sequential calls and time.time() has coarse resolution on some
                # platforms, so {now}:{id(request)} can collide and make zadd
                # overwrite an existing member — under-counting the window and
                # letting callers exceed the limit (fails open). A uuid4 token
                # guarantees each request adds a distinct member.
                pipe.zadd(key, {f"{now}:{uuid.uuid4().hex}": now})
                pipe.zcard(key)
                pipe.expire(key, window)
                _, _, count, _ = await pipe.execute()
        except Exception as exc:  # noqa: BLE001 — fail open on Redis trouble
            logger.warning("rate-limit check skipped (redis unavailable): %s", exc)
            return await call_next(request)

        if count > limit:
            rid = getattr(request.state, "request_id", "")
            return JSONResponse(
                status_code=429,
                content=error_envelope(
                    "RATE_LIMITED",
                    "Too many requests.",
                    details={"limit": limit, "window_seconds": window},
                    request_id=rid,
                ),
                headers={"Retry-After": str(window)},
            )
        return await call_next(request)


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        key = request.headers.get(IDEMPOTENCY_HEADER)
        applies = (
            request.method == "POST"
            and key
            and any(request.url.path.endswith(r) or r in request.url.path for r in IDEMPOTENT_ROUTES)
        )
        if not applies:
            return await call_next(request)

        cache_key = f"idem:{request.url.path}:{key}"
        try:
            r = get_redis()
            cached = await r.get(cache_key)
        except Exception as exc:  # noqa: BLE001 — fail open
            logger.warning("idempotency lookup skipped (redis unavailable): %s", exc)
            return await call_next(request)

        if cached:
            data = json.loads(cached)
            return Response(
                content=data["body"],
                status_code=data["status"],
                media_type=data.get("media_type", "application/json"),
                headers={"Idempotent-Replayed": "true"},
            )

        response = await call_next(request)

        # Only cache successful, fully-buffered responses.
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        if 200 <= response.status_code < 300:
            try:
                await get_redis().set(
                    cache_key,
                    json.dumps(
                        {
                            "status": response.status_code,
                            "body": body.decode("utf-8", "replace"),
                            "media_type": response.media_type,
                            "hash": hashlib.sha256(body).hexdigest(),
                        }
                    ),
                    ex=IDEMPOTENCY_TTL_SECONDS,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("idempotency store skipped (redis unavailable): %s", exc)

        return Response(
            content=body,
            status_code=response.status_code,
            media_type=response.media_type,
            headers=dict(response.headers),
        )


def install_limits(app) -> None:
    """Attach rate-limit + idempotency middleware (registered inside the
    request-id scope set by install_observability)."""
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(RateLimitMiddleware)
