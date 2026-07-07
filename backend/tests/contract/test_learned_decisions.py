"""Two-layer curation KB tests (ADR-0002) — real Postgres via async repos.

Covers the whole loop: a curator's personal decision is remembered, applied to a
new study's pending mappings during harmonize, kept private to its owner, then
admin-promoted to the shared layer where it applies for everyone — with personal
rows still overriding the shared baseline for their owner. Skipped if Postgres
is down.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.db.session as db_session
from app.db.models import Mapping, OntologyMapping, Study, User
from app.repositories import learned_decisions as ld_repo
from app.services.learned_apply import apply_learned_decisions

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def kb_db(database_url):
    engine = create_async_engine(database_url, poolclass=sa.pool.NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("dev Postgres not reachable")
    db_session.engine = engine
    db_session.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    yield db_session.SessionLocal
    await engine.dispose()


async def _mk_user(s, email: str) -> int:
    u = User(email=email, name=email.split("@")[0], role="curator",
             is_active=True, email_verified=True, password_hash="x")
    s.add(u)
    await s.flush()
    return u.id


async def test_personal_scope_and_promotion(kb_db):
    async with kb_db() as s:
        alice = await _mk_user(s, f"alice_{uuid.uuid4().hex[:6]}@example.com")
        bob = await _mk_user(s, f"bob_{uuid.uuid4().hex[:6]}@example.com")
        admin_id = await _mk_user(s, f"admin_{uuid.uuid4().hex[:6]}@example.com")

        key = ld_repo.schema_key("Patient Gender")
        await ld_repo.record_personal(
            s, owner_id=alice, kind="schema", source_key=key,
            decision="accept", target_field="SEX", origin_study_id="s1",
        )
        await s.commit()

        # Personal to Alice: she sees it, Bob doesn't.
        a_hit = await ld_repo.lookup_batch(s, kind="schema", keys=[key], owner_id=alice)
        b_hit = await ld_repo.lookup_batch(s, kind="schema", keys=[key], owner_id=bob)
        assert a_hit[key]["target_field"] == "SEX"
        assert key not in b_hit

        # Repeat confirmation bumps support_count (upsert, not duplicate).
        await ld_repo.record_personal(
            s, owner_id=alice, kind="schema", source_key=key,
            decision="accept", target_field="SEX", origin_study_id="s2",
        )
        await s.commit()

        cands = await ld_repo.promotion_candidates(s)
        assert any(c["source_key"] == key and c["curators"] == 1 for c in cands)

        # Admin promotes -> shared; now Bob sees it too.
        await ld_repo.promote(
            s, kind="schema", source_key=key, decision="accept",
            admin_id=admin_id, target_field="SEX",
        )
        await s.commit()

        b_hit2 = await ld_repo.lookup_batch(s, kind="schema", keys=[key], owner_id=bob)
        assert b_hit2[key]["scope"] == "shared"
        assert b_hit2[key]["target_field"] == "SEX"

        # A promoted candidate drops out of the queue.
        cands2 = await ld_repo.promotion_candidates(s)
        assert not any(c["source_key"] == key for c in cands2)


async def test_personal_overrides_shared(kb_db):
    async with kb_db() as s:
        alice = await _mk_user(s, f"al_{uuid.uuid4().hex[:6]}@example.com")
        admin_id = await _mk_user(s, f"ad_{uuid.uuid4().hex[:6]}@example.com")
        key = ld_repo.ontology_key("body_site", "stool")

        await ld_repo.promote(
            s, kind="ontology", source_key=key, decision="accept",
            admin_id=admin_id, target_term="feces", target_id="UBERON:0001988",
        )
        await ld_repo.record_personal(
            s, owner_id=alice, kind="ontology", source_key=key,
            decision="accept", target_term="intestine", target_id="UBERON:0000160",
        )
        await s.commit()

        hit = await ld_repo.lookup_batch(s, kind="ontology", keys=[key], owner_id=alice)
        assert hit[key]["scope"] == "personal"
        assert hit[key]["target_id"] == "UBERON:0000160"


async def test_apply_learned_decisions_prefills_pending(kb_db):
    async with kb_db() as s:
        alice = await _mk_user(s, f"ap_{uuid.uuid4().hex[:6]}@example.com")
        await ld_repo.record_personal(
            s, owner_id=alice, kind="schema",
            source_key=ld_repo.schema_key("Patient Gender"),
            decision="accept", target_field="SEX",
        )
        await ld_repo.record_personal(
            s, owner_id=alice, kind="ontology",
            source_key=ld_repo.ontology_key("body_site", "stool"),
            decision="accept", target_term="feces", target_id="UBERON:0001988",
        )

        study_id = f"kb_{uuid.uuid4().hex[:8]}"
        s.add(Study(id=study_id, name="KB apply", status="review",
                    file_path=None, owner_id=alice))
        await s.flush()
        s.add(Mapping(study_id=study_id, raw_column="Patient Gender",
                      matched_field="gender", confidence_score=0.4, status="pending"))
        s.add(OntologyMapping(study_id=study_id, field_name="body_site",
                              raw_value="stool", ontology_term=None,
                              confidence_score=0.3, status="pending"))
        await s.commit()

        n = await apply_learned_decisions(s, study_id, alice)
        await s.commit()
        assert n == 2

        m = (await s.execute(
            sa.select(Mapping).where(Mapping.study_id == study_id)
        )).scalar_one()
        assert m.status == "accepted"
        assert m.curator_field == "SEX"

        o = (await s.execute(
            sa.select(OntologyMapping).where(OntologyMapping.study_id == study_id)
        )).scalar_one()
        assert o.status == "accepted"
        assert o.curator_id == "UBERON:0001988"
