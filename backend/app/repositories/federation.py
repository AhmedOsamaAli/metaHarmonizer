"""Federation-lite data access (G1).

Builds the export bundle from this instance's curator-confirmed mappings and
ingests a peer's bundle into the staging tables (pending local approval, Q10).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    FederationImport,
    FederationMapping,
    LearnedDecision,
)
from app.services import federation as fed_sig


def _dedup_key(record_type: str, raw_key: str, target: str, ontology_id: str | None) -> str:
    """Stable content identity for a mapping (per-source dedup)."""
    basis = f"{record_type}|{raw_key.strip().lower()}|{target.strip().lower()}|{(ontology_id or '').strip().lower()}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
async def build_export_records(db: AsyncSession) -> list[dict[str, Any]]:
    """Collect admin-promoted shared human decisions as portable records."""
    records: dict[str, dict[str, Any]] = {}

    stmt = select(LearnedDecision).where(LearnedDecision.scope == "shared")
    for decision in await db.scalars(stmt):
        record_type = f"{decision.kind}_mapping"
        target = (
            decision.target_field if decision.kind == "schema" else decision.target_term
        ) or ""
        key = _dedup_key(record_type, decision.source_key, target, decision.target_id)
        records[key] = {
            "record_type": record_type,
            "raw_key": decision.source_key,
            "decision": decision.decision,
            "accepted_target": target,
            "ontology_id": decision.target_id,
            "confidence_score": None,
            "dedup_key": key,
        }

    return list(records.values())


async def build_export_bundle(db: AsyncSession) -> dict[str, Any]:
    """Build the signed export envelope: payload + signature + source id."""
    from app.core.settings import settings

    records = await build_export_records(db)
    payload = {
        "bundle_version": fed_sig.BUNDLE_VERSION,
        "source_instance": settings.federation_instance_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mappings": records,
    }
    signature = fed_sig.sign_payload(payload)
    return {
        "payload": payload,
        "signature": signature,
        "source_instance": settings.federation_instance_id,
        "public_key": fed_sig.public_key_hex(),
    }


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------
async def record_import(
    db: AsyncSession,
    *,
    payload: dict[str, Any],
    signature: str,
    signature_valid: bool,
    imported_by: int | None,
) -> dict[str, Any]:
    """Persist a received bundle (pending approval) with deduped staged rows.

    Returns a summary dict. Raises ``ValueError`` if this exact bundle
    (payload hash) was already imported.
    """
    source = str(payload.get("source_instance") or "unknown")
    sha = fed_sig.payload_sha256(payload)

    existing = await db.scalar(
        select(FederationImport).where(FederationImport.payload_sha256 == sha)
    )
    if existing is not None:
        raise ValueError("This bundle has already been imported.")

    imp = FederationImport(
        source_instance=source,
        payload_sha256=sha,
        signature=signature,
        signature_valid=signature_valid,
        status="pending",
        imported_by=imported_by,
        mapping_count=0,
    )
    db.add(imp)
    await db.flush()

    # Stage mappings, skipping any already seen from this source (dedup).
    seen_keys = set(
        await db.scalars(
            select(FederationMapping.dedup_key).where(
                FederationMapping.source_instance == source
            )
        )
    )
    added = 0
    for rec in payload.get("mappings", []):
        dedup_key = str(rec.get("dedup_key") or "")
        if not dedup_key or dedup_key in seen_keys:
            continue
        record_type = rec.get("record_type")
        if record_type not in ("schema_mapping", "ontology_mapping"):
            continue
        seen_keys.add(dedup_key)
        decision = str(rec.get("decision") or "accept")
        if decision not in ("accept", "reject"):
            continue
        db.add(
            FederationMapping(
                import_id=imp.id,
                source_instance=source,
                record_type=record_type,
                raw_key=str(rec.get("raw_key") or ""),
                decision=decision,
                accepted_target=str(rec.get("accepted_target") or ""),
                ontology_id=rec.get("ontology_id"),
                confidence_score=rec.get("confidence_score"),
                dedup_key=dedup_key,
            )
        )
        added += 1

    imp.mapping_count = added
    await db.flush()
    return {
        "id": imp.id,
        "source_instance": source,
        "signature_valid": signature_valid,
        "status": imp.status,
        "mapping_count": added,
        "payload_sha256": sha,
    }


def _import_to_dict(imp: FederationImport) -> dict[str, Any]:
    return {
        "id": imp.id,
        "source_instance": imp.source_instance,
        "signature_valid": imp.signature_valid,
        "status": imp.status,
        "mapping_count": imp.mapping_count,
        "imported_by": imp.imported_by,
        "reviewed_by": imp.reviewed_by,
        "reviewed_at": imp.reviewed_at.isoformat() if imp.reviewed_at else None,
        "created_at": imp.created_at.isoformat() if imp.created_at else None,
    }


async def list_imports(
    db: AsyncSession, status: str | None = None
) -> list[dict[str, Any]]:
    stmt = select(FederationImport).order_by(FederationImport.created_at.desc())
    if status:
        stmt = stmt.where(FederationImport.status == status)
    return [_import_to_dict(i) for i in await db.scalars(stmt)]


async def get_import(db: AsyncSession, import_id: int) -> dict[str, Any] | None:
    imp = await db.get(FederationImport, import_id)
    if imp is None:
        return None
    out = _import_to_dict(imp)
    rows = await db.scalars(
        select(FederationMapping).where(FederationMapping.import_id == import_id)
    )
    out["mappings"] = [
        {
            "record_type": r.record_type,
            "raw_key": r.raw_key,
            "decision": r.decision,
            "accepted_target": r.accepted_target,
            "ontology_id": r.ontology_id,
            "confidence_score": r.confidence_score,
        }
        for r in rows
    ]
    return out


async def promote_imported_decisions(
    db: AsyncSession, import_id: int, *, admin_id: int
) -> int:
    rows = list(
        await db.scalars(
            select(FederationMapping).where(FederationMapping.import_id == import_id)
        )
    )
    from app.repositories import learned_decisions as learned_repo

    for row in rows:
        kind = "schema" if row.record_type == "schema_mapping" else "ontology"
        await learned_repo.promote(
            db,
            kind=kind,
            source_key=row.raw_key,
            decision=row.decision,
            admin_id=admin_id,
            target_field=row.accepted_target or None if kind == "schema" else None,
            target_term=row.accepted_target or None if kind == "ontology" else None,
            target_id=row.ontology_id if kind == "ontology" else None,
        )
    return len(rows)


async def set_import_status(
    db: AsyncSession, import_id: int, status: str, reviewed_by: int | None
) -> dict[str, Any] | None:
    imp = await db.get(FederationImport, import_id)
    if imp is None:
        return None
    imp.status = status
    imp.reviewed_by = reviewed_by
    imp.reviewed_at = datetime.now(timezone.utc)
    await db.flush()
    return _import_to_dict(imp)


async def count_pending(db: AsyncSession) -> int:
    return int(
        await db.scalar(
            select(func.count())
            .select_from(FederationImport)
            .where(FederationImport.status == "pending")
        )
        or 0
    )
