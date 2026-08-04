from __future__ import annotations

import uuid

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.core.settings as settings_mod
import app.db.session as db_session
from app.db.models import LearnedDecision, Mapping, OntologyMapping, Study, User
from app.repositories import learned_decisions as ld_repo
from app.services.learned_apply import apply_learned_decisions

from _authflow import register_and_login

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def env(database_url, monkeypatch):
    engine = create_async_engine(database_url, poolclass=sa.pool.NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("dev Postgres not reachable")

    db_session.engine = engine
    db_session.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    import app.core.redis as redis_mod

    redis_mod._client = None
    domain = f"t{uuid.uuid4().hex[:8]}.example.com"
    monkeypatch.setattr(settings_mod.settings, "allowed_email_domains", domain, raising=False)
    monkeypatch.setattr(settings_mod.settings, "hibp_check", False, raising=False)
    monkeypatch.setattr(settings_mod.settings, "auth_mode", "jwt", raising=False)

    from fastapi import FastAPI
    from app.core.middleware import install_observability
    from app.routers import auth, mappings, ontology

    calls: list[dict] = []

    async def fake_rerun(db, **kwargs):
        calls.append(kwargs)
        return {"added": 1, "removed": 0}

    monkeypatch.setattr(mappings, "rerun_column_ontology", fake_rerun)

    app = FastAPI()
    install_observability(app)
    app.include_router(auth.router)
    app.include_router(mappings.router)
    app.include_router(ontology.router)

    def make_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    yield make_client, domain, calls

    async with db_session.SessionLocal() as db:
        await db.execute(sa.delete(Study).where(Study.id.like("accept_sync_%")))
        await db.execute(sa.delete(User).where(User.email.like(f"%@{domain}")))
        await db.commit()
    await engine.dispose()
    redis_mod._client = None


async def _seed(owner_id: int) -> tuple[str, list[int]]:
    study_id = f"accept_sync_{uuid.uuid4().hex[:8]}"
    async with db_session.SessionLocal() as db:
        db.add(
            Study(
                id=study_id,
                name="accept sync",
                status="review",
                file_path="accept_sync.csv",
                owner_id=owner_id,
            )
        )
        await db.flush()
        rows = [
            Mapping(study_id=study_id, raw_column="site", matched_field="body_site", status="pending"),
            Mapping(study_id=study_id, raw_column="gender", matched_field="sex", status="pending"),
            Mapping(study_id=study_id, raw_column="comment", matched_field="notes", status="pending"),
            Mapping(study_id=study_id, raw_column="unused", matched_field="notes", status="pending"),
        ]
        db.add_all(rows)
        await db.flush()
        ids = [row.id for row in rows]
        await db.commit()
    return study_id, ids


async def test_single_and_batch_accept_sync_approved_fields(env):
    make_client, domain, calls = env
    async with make_client() as client:
        await register_and_login(client, f"admin@{domain}")
        curator = await register_and_login(client, f"curator@{domain}")
        headers = {"Authorization": f"Bearer {curator['access_token']}"}
        _, ids = await _seed(curator["user"]["id"])

        response = await client.post(f"/api/v1/mappings/{ids[0]}/accept", headers=headers)
        assert response.status_code == 200
        assert calls[-1]["raw_column"] == "site"
        assert calls[-1]["old_field"] == calls[-1]["new_field"] == "body_site"

        response = await client.post(
            "/api/v1/mappings/batch",
            headers=headers,
            json={"mapping_ids": ids[1:3], "action": "accepted"},
        )
        assert response.status_code == 200
        assert [(call["raw_column"], call["new_field"]) for call in calls] == [
            ("site", "body_site"),
            ("gender", "sex"),
            ("comment", "notes"),
        ]

        before_reject = len(calls)
        response = await client.post(
            "/api/v1/mappings/batch",
            headers=headers,
            json={"mapping_ids": [ids[3]], "action": "rejected"},
        )
        assert response.status_code == 200
        assert len(calls) == before_reject + 1
        assert calls[-1]["raw_column"] == "unused"
        assert calls[-1]["old_field"] == "notes"
        assert calls[-1]["new_field"] is None

        async with db_session.SessionLocal() as db:
            learned = list(
                await db.scalars(
                    sa.select(LearnedDecision).where(
                        LearnedDecision.owner_id == curator["user"]["id"],
                        LearnedDecision.kind == "schema",
                    )
                )
            )
            decisions = {row.source_key: (row.decision, row.target_field) for row in learned}
            assert decisions == {
                ld_repo.schema_key("site"): ("accept", "body_site"),
                ld_repo.schema_key("gender"): ("accept", "sex"),
                ld_repo.schema_key("comment"): ("accept", "notes"),
                ld_repo.schema_key("unused"): ("reject", None),
            }

            next_study = f"accept_sync_{uuid.uuid4().hex[:8]}"
            db.add(Study(id=next_study, name="next", status="review", owner_id=curator["user"]["id"]))
            await db.flush()
            next_rows = [
                Mapping(study_id=next_study, raw_column="site", matched_field="wrong_site", status="accepted"),
                Mapping(study_id=next_study, raw_column="gender", matched_field="wrong_gender", status="accepted"),
                Mapping(study_id=next_study, raw_column="comment", matched_field="wrong_comment", status="pending"),
                Mapping(study_id=next_study, raw_column="unused", matched_field="wrong_unused", status="pending"),
            ]
            db.add_all(next_rows)
            await db.commit()

            assert await apply_learned_decisions(db, next_study, curator["user"]["id"]) == 4
            await db.commit()
            refreshed = list(
                await db.scalars(sa.select(Mapping).where(Mapping.study_id == next_study))
            )
            applied = {row.raw_column: (row.status, row.curator_field) for row in refreshed}
            assert applied == {
                "site": ("accepted", "body_site"),
                "gender": ("accepted", "sex"),
                "comment": ("accepted", "notes"),
                "unused": ("rejected", None),
            }
            assert applied["site"] != ("accepted", "wrong_site")


async def test_ontology_accept_and_reject_apply_to_next_study(env):
    make_client, domain, _calls = env
    async with make_client() as client:
        await register_and_login(client, f"admin2@{domain}")
        curator = await register_and_login(client, f"ontology@{domain}")
        headers = {"Authorization": f"Bearer {curator['access_token']}"}

        first_study = f"accept_sync_{uuid.uuid4().hex[:8]}"
        async with db_session.SessionLocal() as db:
            db.add(Study(id=first_study, name="ontology source", status="review", owner_id=curator["user"]["id"]))
            await db.flush()
            accepted = OntologyMapping(
                study_id=first_study, field_name="body_site", raw_value="lung",
                ontology_term="Lung", ontology_id="UBERON:0002048", status="pending",
            )
            rejected = OntologyMapping(
                study_id=first_study, field_name="disease", raw_value="noise",
                ontology_term="Neoplasm", ontology_id="NCIT:C3262", status="pending",
            )
            db.add_all([accepted, rejected])
            await db.flush()
            accepted_id, rejected_id = accepted.id, rejected.id
            await db.commit()

        assert (
            await client.post(f"/api/v1/ontology/mappings/{accepted_id}/accept", headers=headers)
        ).status_code == 200
        assert (
            await client.post(f"/api/v1/ontology/mappings/{rejected_id}/reject", headers=headers)
        ).status_code == 200

        async with db_session.SessionLocal() as db:
            next_study = f"accept_sync_{uuid.uuid4().hex[:8]}"
            db.add(Study(id=next_study, name="ontology next", status="review", owner_id=curator["user"]["id"]))
            await db.flush()
            db.add_all(
                [
                    OntologyMapping(
                        study_id=next_study, field_name="body_site", raw_value="lung",
                        ontology_term="Wrong Lung", ontology_id="WRONG:1", status="accepted",
                    ),
                    OntologyMapping(
                        study_id=next_study, field_name="disease", raw_value="noise",
                        ontology_term="Wrong Disease", ontology_id="WRONG:2", status="pending",
                    ),
                ]
            )
            await db.commit()

            assert await apply_learned_decisions(db, next_study, curator["user"]["id"]) == 2
            await db.commit()
            rows = list(
                await db.scalars(
                    sa.select(OntologyMapping)
                    .where(OntologyMapping.study_id == next_study)
                    .order_by(OntologyMapping.field_name)
                )
            )
            by_value = {row.raw_value: row for row in rows}
            assert by_value["lung"].status == "accepted"
            assert by_value["lung"].curator_term == "Lung"
            assert by_value["lung"].curator_id == "UBERON:0002048"
            assert by_value["noise"].status == "rejected"
