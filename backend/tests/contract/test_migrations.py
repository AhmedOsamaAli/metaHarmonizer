"""Migration reversibility contract test (prod rollback safety).

Verifies the current head migration is reversible against a throwaway database:
``upgrade head`` -> ``downgrade -1`` -> ``upgrade head`` must all succeed. This
catches a migration shipped without a working ``downgrade`` before it blocks a
production rollback.

Skipped automatically if Postgres is unreachable.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio

BACKEND = Path(__file__).resolve().parents[2]
DBNAME = "mh_migtest"


def _sync_dsn(url: str) -> str:
    return url.replace("+asyncpg", "")


async def _reachable(url: str) -> bool:
    import asyncpg

    try:
        conn = await asyncpg.connect(_sync_dsn(url), timeout=3)
        await conn.close()
        return True
    except Exception:
        return False


async def _admin_exec(base_url: str, sql: str) -> None:
    import asyncpg

    admin = _sync_dsn(base_url).rsplit("/", 1)[0] + "/postgres"
    conn = await asyncpg.connect(admin)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


def _alembic(url: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(BACKEND),
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
    )


async def test_head_migration_is_reversible(database_url):
    if not await _reachable(database_url):
        pytest.skip("dev Postgres not reachable (run scripts/dev_services.ps1 start)")

    base = database_url.rsplit("/", 1)[0]
    throwaway = f"{base}/{DBNAME}"

    await _admin_exec(database_url, f'DROP DATABASE IF EXISTS "{DBNAME}"')
    await _admin_exec(database_url, f'CREATE DATABASE "{DBNAME}"')
    try:
        up1 = _alembic(throwaway, "upgrade", "head")
        assert up1.returncode == 0, up1.stderr

        down = _alembic(throwaway, "downgrade", "-1")
        assert down.returncode == 0, down.stderr

        up2 = _alembic(throwaway, "upgrade", "head")
        assert up2.returncode == 0, up2.stderr

        # Sanity: schema is intact at head after the round-trip.
        import asyncpg

        conn = await asyncpg.connect(_sync_dsn(throwaway))
        try:
            studies_exists = await conn.fetchval(
                "SELECT to_regclass('public.studies') IS NOT NULL"
            )
        finally:
            await conn.close()
        assert studies_exists is True
    finally:
        # Terminate any lingering backends, then drop the throwaway DB.
        await _admin_exec(
            database_url,
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{DBNAME}' AND pid <> pg_backend_pid()",
        )
        await _admin_exec(database_url, f'DROP DATABASE IF EXISTS "{DBNAME}"')
