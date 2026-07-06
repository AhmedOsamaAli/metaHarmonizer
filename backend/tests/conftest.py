"""Shared pytest fixtures.

Database tests run against an isolated ``*_test`` database (provisioned +
migrated once per session, truncated between tests) so they never touch the
dev DB's data and the bootstrap-admin assumption stays deterministic. If the
test DB can't be provisioned (or Postgres is down) the fixtures fall back to
the configured DATABASE_URL and per-test tests skip on unreachability.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Ensure a valid JWT secret for any settings import during tests.
os.environ.setdefault("JWT_SECRET", "test-secret-key-at-least-32-bytes-long!!")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://mh:mh_dev_password@127.0.0.1:5433/metaharmonizer",
)
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6380/0")


def _sync_dsn(async_url: str) -> str:
    return async_url.replace("+asyncpg", "")


def _derive_test_url(url: str) -> str:
    base, sep, dbname = url.rpartition("/")
    return f"{base}{sep}{dbname}_test"


async def _ensure_database(orig_url: str, test_url: str) -> None:
    import asyncpg

    admin_dsn = _sync_dsn(orig_url).rsplit("/", 1)[0] + "/postgres"
    dbname = test_url.rsplit("/", 1)[-1]
    conn = await asyncpg.connect(admin_dsn)
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", dbname):
            await conn.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        await conn.close()


async def _truncate_all(async_url: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(_sync_dsn(async_url))
    try:
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' "
            "AND tablename <> 'alembic_version'"
        )
        tables = [r["tablename"] for r in rows]
        if tables:
            await conn.execute(
                "TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE"
            )
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def _isolated_test_db():
    """Provision + migrate a ``*_test`` database and route the suite at it."""
    orig = os.environ["DATABASE_URL"]
    if orig.rsplit("/", 1)[-1].endswith("_test"):
        yield
        return

    test_url = _derive_test_url(orig)
    try:
        asyncio.run(_ensure_database(orig, test_url))
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(Path(__file__).resolve().parents[1]),
            env={**os.environ, "DATABASE_URL": test_url},
            check=True,
            capture_output=True,
        )
    except Exception:
        yield  # provisioning failed → leave the dev DB; nothing worse than before
        return

    os.environ["DATABASE_URL"] = test_url
    # Rebind the app's cached settings + session engine (both captured the dev
    # URL at import, before this fixture ran) so *every* code path uses the
    # isolated test DB. Modules that did ``from app.db.session import SessionLocal``
    # hold the sessionmaker object by value, so we reconfigure it in place
    # (``.configure(bind=...)``) rather than replacing the attribute.
    import app.core.settings as settings_mod
    import app.db.session as db_session
    from sqlalchemy.ext.asyncio import create_async_engine

    orig_engine = db_session.engine
    session_maker = db_session.SessionLocal
    settings_mod.settings.database_url = test_url
    db_session.engine = create_async_engine(test_url, pool_pre_ping=True)
    session_maker.configure(bind=db_session.engine)
    try:
        yield
    finally:
        os.environ["DATABASE_URL"] = orig
        settings_mod.settings.database_url = orig
        session_maker.configure(bind=orig_engine)
        db_session.engine = orig_engine


@pytest.fixture(autouse=True)
def _truncate_between_tests():
    """Reset the isolated test DB after each test for full isolation."""
    yield
    url = os.environ.get("DATABASE_URL", "")
    if url.rsplit("/", 1)[-1].endswith("_test"):
        try:
            asyncio.run(_truncate_all(url))
        except Exception:
            pass


@pytest.fixture(scope="session")
def database_url() -> str:
    return os.environ["DATABASE_URL"]
