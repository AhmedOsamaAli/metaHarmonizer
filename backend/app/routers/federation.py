"""Federation-lite router (G1) — ``/api/v1/federation``.

Two deploying institutions exchange a signed JSON bundle of curator-confirmed
mappings. Admin-only on both sides. Imports are never auto-merged: they land
``pending`` and an admin approves or rejects (Q10 two-stage approval).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import actor_label, require_role
from app.db.models import User
from app.db.session import get_db
from app.repositories import audit as audit_repo
from app.repositories import federation as fed_repo
from app.services import federation as fed_sig

router = APIRouter(prefix="/api/v1/federation", tags=["federation"])


@router.get("/public-key")
async def federation_public_key(_admin: User = Depends(require_role("admin"))) -> dict[str, str]:
    """This instance's id + Ed25519 public key — share it with peers to be trusted."""
    from app.core.settings import settings

    return {
        "instance_id": settings.federation_instance_id,
        "public_key": fed_sig.public_key_hex(),
    }


@router.get("/export")
async def federation_export(
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Emit a signed bundle of this instance's curator-confirmed mappings."""
    bundle = await fed_repo.build_export_bundle(db)
    await audit_repo.add_audit_entry(
        db,
        study_id="",
        action="federation_export",
        new_value=str(len(bundle["payload"]["mappings"])),
        actor_id=admin.id,
        curator=actor_label(admin),
    )
    await db.commit()
    return bundle


@router.post("/import")
async def federation_import(
    bundle: dict[str, Any] = Body(...),
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Ingest a peer's signed bundle. Verified, deduped, and left pending.

    The signature is verified against the trusted-peer registry; an invalid or
    untrusted signature is rejected outright (never staged).
    """
    payload = bundle.get("payload")
    signature = bundle.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature, str):
        raise HTTPException(status_code=400, detail="Bundle needs 'payload' and 'signature'.")

    source = str(payload.get("source_instance") or "unknown")
    signature_valid = fed_sig.verify_payload(payload, signature, source)
    if not signature_valid:
        raise HTTPException(
            status_code=400,
            detail=f"Signature invalid or source '{source}' is not a trusted peer.",
        )

    try:
        fed_sig.check_freshness(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        summary = await fed_repo.record_import(
            db,
            payload=payload,
            signature=signature,
            signature_valid=signature_valid,
            imported_by=admin.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await audit_repo.add_audit_entry(
        db,
        study_id="",
        action="federation_import",
        new_value=f"{source}:{summary['mapping_count']}",
        actor_id=admin.id,
        curator=actor_label(admin),
    )
    await db.commit()
    return summary


@router.get("/imports")
async def federation_list_imports(
    status: str | None = None,
    _admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List received bundles (optionally filtered by status)."""
    return await fed_repo.list_imports(db, status=status)


@router.get("/imports/{import_id}")
async def federation_get_import(
    import_id: int,
    _admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One received bundle with its staged mappings."""
    out = await fed_repo.get_import(db, import_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Import not found.")
    return out


@router.post("/imports/{import_id}/approve")
async def federation_approve_import(
    import_id: int,
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Approve a pending import into the local knowledge base (Q10)."""
    return await _review_import(db, import_id, "approved", admin)


@router.post("/imports/{import_id}/reject")
async def federation_reject_import(
    import_id: int,
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Reject a pending import; its staged mappings stay recorded but inactive."""
    return await _review_import(db, import_id, "rejected", admin)


async def _review_import(
    db: AsyncSession, import_id: int, status: str, admin: User
) -> dict[str, Any]:
    existing = await fed_repo.get_import(db, import_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Import not found.")
    if existing["status"] != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Import already {existing['status']}.",
        )
    out = await fed_repo.set_import_status(db, import_id, status, reviewed_by=admin.id)
    if status == "approved":
        await fed_repo.promote_imported_decisions(db, import_id, admin_id=admin.id)
    await audit_repo.add_audit_entry(
        db,
        study_id="",
        action=f"federation_{status}",
        new_value=str(import_id),
        actor_id=admin.id,
        curator=actor_label(admin),
    )
    await db.commit()
    return out
