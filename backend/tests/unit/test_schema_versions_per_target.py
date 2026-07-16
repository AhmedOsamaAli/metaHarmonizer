"""Per-target schema-version invariants (U9).

Each engine target schema keeps its own *current* version, and seeding creates
one ``v1`` lineage per installed target. Runs against the isolated ``*_test``
Postgres provisioned by conftest; skips if it isn't reachable. Uses a per-test
NullPool engine (like the schema-diff contract test) to avoid cross-event-loop
connection reuse between async tests.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.repositories import schema_versions as repo

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def sf(database_url):
    engine = create_async_engine(database_url, poolclass=sa.pool.NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("test Postgres not reachable")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield maker
    finally:
        await engine.dispose()


async def test_current_is_isolated_per_target(sf):
    async with sf() as db:
        await repo.create_version(
            db, label="v1", source_path="/tmp/gdc_v1.csv",
            target_schema="gdc", make_current=True,
        )
        await repo.create_version(
            db, label="v1", source_path="/tmp/cbio_v1.csv",
            target_schema="cbioportal", make_current=True,
        )
        # A second gdc version becomes gdc's current...
        await repo.create_version(
            db, label="v2", source_path="/tmp/gdc_v2.csv",
            target_schema="gdc", make_current=True,
        )
        await db.commit()

        gdc_current = await repo.get_current(db, "gdc")
        cbio_current = await repo.get_current(db, "cbioportal")
        assert gdc_current is not None and gdc_current.label == "v2"
        # ...without disturbing cbioportal's current.
        assert cbio_current is not None and cbio_current.label == "v1"

        # Exactly one current per target.
        gdc_all = await repo.list_versions(db, "gdc")
        assert sum(1 for v in gdc_all if v["is_current"]) == 1


async def test_ensure_seed_versions_is_per_target_and_idempotent(sf):
    targets = {"gdc": "/tmp/gdc.csv", "cbioportal": "/tmp/cbio.csv"}
    async with sf() as db:
        await repo.ensure_seed_versions(db, targets)
    async with sf() as db:
        # Second call is a no-op (each target already has a version).
        await repo.ensure_seed_versions(db, targets)
        for key in targets:
            cur = await repo.get_current(db, key)
            assert cur is not None and cur.label == "v1"
        v1s = [v for v in await repo.list_versions(db) if v["label"] == "v1"]
        assert len(v1s) == 2
