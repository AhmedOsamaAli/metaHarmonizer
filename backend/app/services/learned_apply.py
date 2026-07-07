"""Apply the two-layer curation KB during harmonize (ADR-0002 — read path).

After the engine produces a study's mappings, pre-apply any remembered curator
decisions (personal → shared precedence) so curators stop re-deciding the same
obvious mappings. Every KB-driven application writes a ``kb_apply`` audit row,
so it is fully traceable (ADR: "never silent"). Only fresh ``pending`` rows are
touched — a decision already made on this study is never overwritten.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import audit as audit_repo
from app.repositories import learned_decisions as ld_repo
from app.repositories import mappings as mappings_repo
from app.repositories import ontology as ontology_repo

logger = logging.getLogger(__name__)


async def apply_learned_decisions(
    db: AsyncSession, study_id: str, owner_id: int | None
) -> int:
    """Pre-apply remembered decisions to ``study_id``'s pending mappings.

    Returns the number of rows the KB touched. The caller commits.
    """
    if owner_id is None:
        return 0

    applied = 0

    # ── Schema (column-name) decisions ──────────────────────────────────────
    schema = await mappings_repo.get_mappings(db, study_id)
    schema_keys = {
        m["id"]: ld_repo.schema_key(m["raw_column"])
        for m in schema
        if m.get("raw_column")
    }
    schema_hits = await ld_repo.lookup_batch(
        db, kind="schema", keys=list(set(schema_keys.values())), owner_id=owner_id
    )
    for m in schema:
        if m.get("status") not in (None, "pending"):
            continue
        hit = schema_hits.get(schema_keys.get(m["id"]))
        if not hit:
            continue
        if hit["decision"] == "reject":
            await mappings_repo.update_mapping_status(
                db, m["id"], "rejected", reviewed_by=owner_id
            )
        else:
            await mappings_repo.update_mapping_status(
                db, m["id"], "accepted",
                curator_field=hit.get("target_field") or None,
                reviewed_by=owner_id,
            )
        await audit_repo.add_audit_entry(
            db, study_id=study_id, action="kb_apply", mapping_id=m["id"],
            old_value=m.get("status"), new_value=hit["decision"],
            actor_id=owner_id, curator=f"learned:{hit['scope']}#{hit['id']}",
        )
        applied += 1

    # ── Ontology (value) decisions ──────────────────────────────────────────
    onto = await ontology_repo.get_ontology_mappings(db, study_id)
    onto_keys = {
        o["id"]: ld_repo.ontology_key(o.get("field_name") or "", o.get("raw_value") or "")
        for o in onto
    }
    onto_hits = await ld_repo.lookup_batch(
        db, kind="ontology", keys=list(set(onto_keys.values())), owner_id=owner_id
    )
    for o in onto:
        if o.get("status") not in (None, "pending"):
            continue
        hit = onto_hits.get(onto_keys.get(o["id"]))
        if not hit:
            continue
        if hit["decision"] == "reject":
            await ontology_repo.update_ontology_mapping(
                db, o["id"], status="rejected", reviewed_by=owner_id
            )
        else:
            await ontology_repo.update_ontology_mapping(
                db, o["id"], status="accepted",
                curator_term=hit.get("target_term"),
                curator_id=hit.get("target_id"),
                reviewed_by=owner_id,
            )
        await audit_repo.add_audit_entry(
            db, study_id=study_id, action="kb_apply", mapping_id=o["id"],
            old_value=o.get("status"), new_value=hit["decision"],
            actor_id=owner_id, curator=f"learned:{hit['scope']}#{hit['id']}",
        )
        applied += 1

    return applied
