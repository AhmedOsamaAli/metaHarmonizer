"""Harmonize idempotency / active-dedup contract tests.

Covers the double-submit guard added for production hardening:
  - ``studies_repo.find_active_by_content`` finds an owner's in-flight study,
  - the ``uq_studies_active_content`` partial unique index rejects a *second*
    ACTIVE study for the same (owner, content-hash) — the concurrent-race guard,
  - the dedup window releases once the prior run leaves the active states, so
    the same file can be re-harmonized later.

Skipped automatically if the dev Postgres is not reachable.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import Study, User
from app.repositories import studies as studies_repo

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def session(database_url):
    engine = create_async_engine(database_url, poolclass=sa.pool.NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("dev Postgres not reachable (run scripts/dev_services.ps1 start)")

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _make_owner(session) -> int:
    user = User(email=f"dedup_{uuid.uuid4().hex[:8]}@example.com", role="curator")
    session.add(user)
    await session.commit()
    return user.id


async def test_active_content_dedup(session):
    owner_id = await _make_owner(session)
    sha = uuid.uuid4().hex + uuid.uuid4().hex  # 64-char stand-in hash
    sid_a = f"dupA_{uuid.uuid4().hex[:8]}"

    await studies_repo.create_study(
        session,
        study_id=sid_a,
        name="dedup A",
        file_path=f"{sid_a}.csv",
        row_count=3,
        column_count=2,
        owner_id=owner_id,
        content_sha256=sha,
    )
    await studies_repo.update_status(session, sid_a, "queued")
    await session.commit()

    # The in-flight study is discoverable by (owner, content-hash).
    found = await studies_repo.find_active_by_content(
        session, owner_id=owner_id, content_sha256=sha
    )
    assert found is not None and found["id"] == sid_a

    # A second ACTIVE study for the same owner+content is rejected by the
    # partial unique index (this is the concurrent double-submit guard).
    session.add(
        Study(
            id=f"dupB_{uuid.uuid4().hex[:8]}",
            name="dedup B",
            status="queued",
            owner_id=owner_id,
            content_sha256=sha,
        )
    )
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()

    # Once the first study leaves the active window, the same file is allowed
    # again (deliberate re-harmonization is not blocked).
    await studies_repo.update_status(session, sid_a, "review")
    await session.commit()
    assert (
        await studies_repo.find_active_by_content(
            session, owner_id=owner_id, content_sha256=sha
        )
        is None
    )
    sid_c = f"dupC_{uuid.uuid4().hex[:8]}"
    await studies_repo.create_study(
        session,
        study_id=sid_c,
        name="dedup C",
        file_path=f"{sid_c}.csv",
        row_count=3,
        column_count=2,
        owner_id=owner_id,
        content_sha256=sha,
    )
    await studies_repo.update_status(session, sid_c, "queued")
    await session.commit()

    # cleanup
    await session.execute(sa.delete(Study).where(Study.id.in_([sid_a, sid_c])))
    await session.execute(sa.delete(User).where(User.id == owner_id))
    await session.commit()


async def test_anonymous_uploads_are_not_deduped(session):
    # NULL owner_id must never dedup — SQL treats NULLs as distinct, matching
    # the partial unique index, so anonymous uploads always create new studies.
    sha = uuid.uuid4().hex + uuid.uuid4().hex
    assert (
        await studies_repo.find_active_by_content(
            session, owner_id=None, content_sha256=sha
        )
        is None
    )
