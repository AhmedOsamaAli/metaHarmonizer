"""Federation-lite tests (G1) against the dev Postgres.

Covers the full flow: build a signed export bundle, verify the signature,
import it (deduped, pending), reject an out-of-trust / tampered bundle, refuse a
duplicate bundle, and approve/reject a pending import (Q10). Skipped if Postgres
is down.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.db.session as db_session
from app.db.models import LearnedDecision, Mapping, OntologyMapping, Study, User

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def fed_app(database_url):
    engine = create_async_engine(database_url, poolclass=sa.pool.NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("dev Postgres not reachable")

    db_session.engine = engine
    db_session.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    # Seed one study with an accepted schema mapping + an accepted ontology
    # mapping — the export should pick exactly these up.
    study_id = f"fed_{uuid.uuid4().hex[:8]}"
    async with db_session.SessionLocal() as s:
        admin = User(
            email=f"fedadmin_{uuid.uuid4().hex[:8]}@test.local",
            name="Fed Admin",
            role="admin",
            is_active=True,
            email_verified=True,
        )
        s.add(admin)
        await s.flush()
        admin_id = admin.id
        s.add(Study(id=study_id, name="Fed Test", status="review", file_path=None))
        await s.flush()
        s.add(
            Mapping(
                study_id=study_id,
                raw_column=f"gender_{study_id}",
                matched_field="sex",
                confidence_score=0.99,
                status="accepted",
            )
        )
        s.add_all(
            [
                LearnedDecision(
                    scope="shared", owner_id=None, kind="schema",
                    source_key=f"gender {study_id}", decision="accept",
                    target_field="sex", promoted_by=admin_id,
                ),
                LearnedDecision(
                    scope="shared", owner_id=None, kind="ontology",
                    source_key=f"sex::male {study_id}", decision="accept",
                    target_term="Male", target_id="NCIT:C20197", promoted_by=admin_id,
                ),
                LearnedDecision(
                    scope="shared", owner_id=None, kind="schema",
                    source_key=f"noise {study_id}", decision="reject",
                    promoted_by=admin_id,
                ),
                LearnedDecision(
                    scope="personal", owner_id=admin_id, kind="schema",
                    source_key=f"private {study_id}", decision="accept",
                    target_field="private_field",
                ),
            ]
        )
        s.add(
            OntologyMapping(
                study_id=study_id,
                field_name="sex",
                raw_value=f"male_{study_id}",
                ontology_term="Male",
                ontology_id="NCIT:C20197",
                confidence_score=1.0,
                status="accepted",
            )
        )
        await s.commit()

    from fastapi import FastAPI
    from app.core.deps import current_user
    from app.core.middleware import install_observability
    from app.routers import federation

    app = FastAPI()
    install_observability(app)
    app.include_router(federation.router)
    app.dependency_overrides[current_user] = lambda: User(
        id=admin_id, email="admin@test.local", role="admin"
    )

    yield app, study_id

    async with db_session.SessionLocal() as s:
        await s.execute(sa.text("DELETE FROM federation_mappings"))
        await s.execute(sa.text("DELETE FROM federation_imports"))
        await s.execute(sa.text("DELETE FROM learned_decisions WHERE source_key LIKE :key"), {"key": f"%{study_id}"})
        await s.execute(sa.text("DELETE FROM mappings WHERE study_id = :sid"), {"sid": study_id})
        await s.execute(sa.text("DELETE FROM ontology_mappings WHERE study_id = :sid"), {"sid": study_id})
        await s.execute(sa.text("DELETE FROM studies WHERE id = :sid"), {"sid": study_id})
        await s.execute(sa.text("DELETE FROM users WHERE id = :uid"), {"uid": admin_id})
        await s.commit()
    await engine.dispose()


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_export_is_signed_and_contains_accepted_mappings(fed_app):
    app, study_id = fed_app
    async with _client(app) as client:
        r = await client.get("/api/v1/federation/export")
    assert r.status_code == 200
    bundle = r.json()
    assert bundle["signature"]
    assert bundle["public_key"]
    records = bundle["payload"]["mappings"]
    targets = {m["accepted_target"] for m in records}
    assert "sex" in targets  # schema mapping
    assert "Male" in targets  # ontology mapping
    assert any(m["decision"] == "reject" for m in records)
    assert not any(m["raw_key"].startswith("private") for m in records)


async def test_self_export_import_roundtrip_pending(fed_app):
    app, study_id = fed_app
    async with _client(app) as client:
        exported = (await client.get("/api/v1/federation/export")).json()
        r = await client.post("/api/v1/federation/import", json=exported)
        assert r.status_code == 200, r.text
        summary = r.json()
        assert summary["signature_valid"] is True
        assert summary["status"] == "pending"  # never auto-merged
        assert summary["mapping_count"] >= 2

        imports = (await client.get("/api/v1/federation/imports", params={"status": "pending"})).json()
        assert any(i["id"] == summary["id"] for i in imports)


async def test_tampered_payload_is_rejected(fed_app):
    app, study_id = fed_app
    async with _client(app) as client:
        exported = (await client.get("/api/v1/federation/export")).json()
        # Tamper: add a mapping after signing -> signature no longer matches.
        exported["payload"]["mappings"].append(
            {
                "record_type": "schema_mapping",
                "raw_key": "evil",
                "accepted_target": "evil_field",
                "ontology_id": None,
                "confidence_score": 1.0,
                "dedup_key": "evilkey",
            }
        )
        r = await client.post("/api/v1/federation/import", json=exported)
    assert r.status_code == 400
    assert "Signature invalid" in r.json()["error"]["message"]


async def test_untrusted_source_is_rejected(fed_app):
    app, study_id = fed_app
    async with _client(app) as client:
        exported = (await client.get("/api/v1/federation/export")).json()
        exported["payload"]["source_instance"] = "stranger-instance"
        r = await client.post("/api/v1/federation/import", json=exported)
    assert r.status_code == 400


async def test_duplicate_bundle_is_conflict(fed_app):
    app, study_id = fed_app
    async with _client(app) as client:
        exported = (await client.get("/api/v1/federation/export")).json()
        first = await client.post("/api/v1/federation/import", json=exported)
        assert first.status_code == 200
        second = await client.post("/api/v1/federation/import", json=exported)
    assert second.status_code == 409


async def test_approve_flow(fed_app):
    app, study_id = fed_app
    async with _client(app) as client:
        exported = (await client.get("/api/v1/federation/export")).json()
        imp = (await client.post("/api/v1/federation/import", json=exported)).json()
        approved = await client.post(f"/api/v1/federation/imports/{imp['id']}/approve")
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"
        async with db_session.SessionLocal() as s:
            shared = list(
                await s.scalars(
                    sa.select(LearnedDecision).where(
                        LearnedDecision.scope == "shared",
                        LearnedDecision.source_key.in_(
                            [f"gender {study_id}", f"sex::male {study_id}", f"noise {study_id}"]
                        ),
                    )
                )
            )
            assert {row.source_key: row.decision for row in shared} == {
                f"gender {study_id}": "accept",
                f"sex::male {study_id}": "accept",
                f"noise {study_id}": "reject",
            }
        # Approving again is a conflict (already reviewed).
        again = await client.post(f"/api/v1/federation/imports/{imp['id']}/approve")
        assert again.status_code == 409
