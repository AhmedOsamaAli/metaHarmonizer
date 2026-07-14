"""Create a Postgres database if it doesn't exist. Usage: python -m scripts.ensure_db <dbname>

Small helper used by the dashboard/benchmark runner scripts so a fresh checkout
can stand up an isolated DB without manual psql. Reads the admin DSN from
``ADMIN_DSN`` (default: the dev Postgres on :5433).
"""

from __future__ import annotations

import asyncio
import os
import sys


async def _main(dbname: str) -> None:
    import asyncpg

    admin = os.environ.get("ADMIN_DSN", "postgresql://mh:mh_dev_password@127.0.0.1:5433/postgres")
    conn = await asyncpg.connect(admin)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", dbname)
        if exists:
            print(f"database {dbname} exists")
        else:
            await conn.execute(f'CREATE DATABASE "{dbname}"')
            print(f"created database {dbname}")
    finally:
        await conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m scripts.ensure_db <dbname>", file=sys.stderr)
        raise SystemExit(2)
    asyncio.run(_main(sys.argv[1]))
