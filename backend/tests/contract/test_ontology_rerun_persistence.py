from __future__ import annotations

from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import OntologyMapping, Study
from app.repositories import ontology as ontology_repo


@pytest.mark.asyncio
async def test_delete_stale_ontology_preserves_human_review(database_url):
    engine = create_async_engine(database_url, poolclass=sa.pool.NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as db:
            db.add(Study(id="ontology-rerun", name="rerun", status="review"))
            await db.flush()
            db.add_all(
                [
                    OntologyMapping(
                        study_id="ontology-rerun",
                        field_name="body_site",
                        raw_value="lung",
                        ontology_term="Lung",
                        status="accepted",
                    ),
                    OntologyMapping(
                        study_id="ontology-rerun",
                        field_name="body_site",
                        raw_value="liver",
                        ontology_term="Liver",
                        status="accepted",
                        reviewed_at=datetime.now(timezone.utc),
                    ),
                ]
            )
            await db.commit()

            removed = await ontology_repo.delete_unreviewed_ontology(
                db,
                "ontology-rerun",
                {"body_site", "notes"},
                {"lung", "liver"},
            )
            await db.commit()

            rows = await ontology_repo.get_ontology_mappings(db, "ontology-rerun")
            assert removed == 1
            assert [(row["raw_value"], row["reviewed_at"] is not None) for row in rows] == [
                ("liver", True)
            ]
    finally:
        await engine.dispose()