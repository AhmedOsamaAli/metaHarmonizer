"""
MetaHarmonizer Dashboard — FastAPI Application

Main entry point. Configures logging, the unified error envelope + request-id
middleware, then registers all routers.
"""

import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.logging import configure_logging
from app.core.middleware import SecurityHeadersMiddleware, install_observability
from app.core.limits import install_limits
from app.core.metrics import MetricsMiddleware
from app.core.sentry import init_sentry
from app.core.settings import settings
from app.routers import admin, audit, auth, export, federation, harmonize, health, mappings, ontology, quality, tokens, ws

configure_logging(settings.log_level)
init_sentry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-warm the ML engine on startup. The database schema is managed by
    Alembic migrations (run before boot), so there's no runtime DDL here."""
    # Pre-warm the engine in a background thread (loads the ~90 MB
    # SentenceTransformer + dicts and warms the NCI cache) so the server
    # accepts requests immediately and the first upload isn't cold.
    def _warm():
        from app.engine_adapter import get_engine
        get_engine().pre_warm()

    t = threading.Thread(target=_warm, daemon=True)
    t.start()

    # Seed the bootstrap schema version (v1) so every study can be stamped with
    # a reproducibility pin. Idempotent: no-op once a current version exists.
    try:
        from app.db.session import SessionLocal
        from app.engine_adapter import _schema_registry
        from app.repositories import schema_versions as schema_repo
        from app.routers.harmonize import CURATED_PATH

        # One v1 lineage per installed target schema (gdc / cbioportal / cmd / …),
        # falling back to the default key when no registry is installed.
        keys = [s["key"] for s in _schema_registry.available_schemas()] or [
            _schema_registry.default_key()
        ]
        targets = {k: str(CURATED_PATH) for k in keys}
        async with SessionLocal() as db:
            await schema_repo.ensure_seed_versions(db, targets)
    except Exception:  # noqa: BLE001 — seeding must never block startup
        import logging

        logging.getLogger("app").warning("schema version seed skipped", exc_info=True)

    # Seed / bump the current ontology snapshot — the reproducibility pin for the
    # KB bundle in effect (engine version + bundle sha). Idempotent: unchanged if
    # the identity matches; bumps to a new current snapshot on a KB refresh or
    # engine upgrade. New studies are stamped with the current snapshot.
    try:
        import os
        from importlib.metadata import PackageNotFoundError
        from importlib.metadata import version as _pkg_version

        from app.db.session import SessionLocal
        from app.repositories import ontology_snapshots as onto_repo

        try:
            engine_version = _pkg_version("metaharmonizer")
        except PackageNotFoundError:
            engine_version = None
        kb_source = os.environ.get("KB_BUNDLE_SHA256") or None
        async with SessionLocal() as db:
            await onto_repo.ensure_current(db, engine_version=engine_version, source=kb_source)
            await db.commit()
    except Exception:  # noqa: BLE001 — seeding must never block startup
        import logging

        logging.getLogger("app").warning("ontology snapshot seed skipped", exc_info=True)

    yield


app = FastAPI(
    title="MetaHarmonizer Dashboard API",
    description="Automated metadata harmonization for cBioPortal — curator review dashboard backend.",
    version="0.1.0",
    lifespan=lifespan,
    redoc_url=None,
)

# Request-id + unified error envelope (spec §6.1).
install_observability(app)

# Static security headers on every response (defense-in-depth behind any proxy).
app.add_middleware(SecurityHeadersMiddleware)

# Prometheus golden-signal instrumentation (exposed at admin-scoped /metrics).
app.add_middleware(MetricsMiddleware)

# Rate-limit + idempotency (spec §6.4); fail-open if Redis is unavailable.
install_limits(app)

# CORS — restricted origins (no wildcards in production) + explicit methods/headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)

# Register routers
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(tokens.router)
app.include_router(ws.router)
app.include_router(audit.router)
app.include_router(harmonize.router)
app.include_router(mappings.router)
app.include_router(quality.router)
app.include_router(export.router)
app.include_router(federation.router)
app.include_router(ontology.router)


@app.get("/", tags=["health"])
async def root():
    return {
        "service": "MetaHarmonizer Dashboard API",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}


@app.get("/config", tags=["config"])
@app.get("/api/v1/config", tags=["config"])
async def config():
    """Public feature flags the SPA reads to hide capabilities the server lacks."""
    return {"llm_enabled": settings.llm_enabled}


@app.get("/health/engine", tags=["health"])
async def health_engine():
    """Report which engine adapter is active and whether it is ready."""
    from app.engine_adapter import get_engine

    return get_engine().health().model_dump()
