from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import EngineProposal
from app.repositories import engine_proposals as proposals


@pytest.mark.asyncio
async def test_engine_proposals_upsert_and_version_scope(database_url):
    engine = create_async_engine(database_url, poolclass=sa.pool.NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as db:
            await proposals.upsert_many(
                db,
                scope_key="schema:v1:1:0.4.1",
                kind="schema",
                proposals={"gender": {"matched_field": "sex", "confidence_score": 0.9}},
                engine_version="0.4.1",
            )
            await proposals.upsert_many(
                db,
                scope_key="schema:v1:1:0.4.1",
                kind="schema",
                proposals={"gender": {"matched_field": "sex", "confidence_score": 0.95}},
                engine_version="0.4.1",
            )
            await proposals.upsert_many(
                db,
                scope_key="schema:v1:1:0.5.0",
                kind="schema",
                proposals={"gender": {"matched_field": "biological_sex", "confidence_score": 0.8}},
                engine_version="0.5.0",
            )
            await db.commit()

            current = await proposals.lookup(
                db,
                scope_key="schema:v1:1:0.4.1",
                kind="schema",
                keys=["gender"],
            )
            upgraded = await proposals.lookup(
                db,
                scope_key="schema:v1:1:0.5.0",
                kind="schema",
                keys=["gender"],
            )
            await db.commit()

            assert current["gender"]["confidence_score"] == 0.95
            assert upgraded["gender"]["matched_field"] == "biological_sex"
            count = await db.scalar(
                sa.select(sa.func.count()).select_from(EngineProposal).where(
                    EngineProposal.kind == "schema",
                    EngineProposal.source_key == "gender",
                )
            )
            assert count == 2
    finally:
        await engine.dispose()
