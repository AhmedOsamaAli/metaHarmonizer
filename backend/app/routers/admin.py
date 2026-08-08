"""
Admin router (Sprint 3, slice 3) — user management, RBAC-protected.

Every endpoint here requires the ``admin`` role via ``require_role("admin")``,
which demonstrates the role-based access control built in ``app.core.deps``.
When ``AUTH_MODE=none`` the dependency yields a synthetic admin, so these
routes remain reachable for local development.
"""

from __future__ import annotations

import io
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ForbiddenError, actor_label, require_role
from app.core.email import send_account_approved_email, send_account_rejected_email
from app.core.errors import NotFoundError
from app.db.models import SchemaVersion, User
from app.db.session import get_db
from app.repositories import audit as audit_repo
from app.repositories import learned_decisions as ld_repo
from app.repositories import schema_versions as schema_repo
from app.repositories import sessions as sessions_repo
from app.repositories import users as users_repo
from app.schemas.auth import ActiveUpdate, RoleUpdate, UserOut

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# New schema CSVs are stored alongside the seed curated file.
SCHEMA_STORE = Path(__file__).resolve().parent.parent.parent / "data" / "schema" / "versions"
# Admin-uploaded column-name alias dictionary (engine long format), read by the
# engine adapter when constructing the schema mapper.
ALIAS_STORE = Path(__file__).resolve().parent.parent.parent / "data" / "schema" / "aliases"
ALIAS_FILE = ALIAS_STORE / "current.alias.csv"


def _new_schema_upload_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return SCHEMA_STORE / f"curated_{stamp}_{uuid.uuid4().hex}.csv"


@router.get("/users", response_model=list[UserOut])
async def list_users(
    _admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> list[UserOut]:
    rows = await users_repo.list_users(db)
    return [UserOut.model_validate(u) for u in rows]


@router.patch("/users/{user_id}/role", response_model=UserOut)
async def set_role(
    user_id: int,
    body: RoleUpdate,
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    user = await users_repo.get_by_id(db, user_id)
    if not user:
        raise NotFoundError("User not found.")
    if user.id == admin.id and body.role != "admin":
        # Guard against an admin accidentally demoting themselves and locking
        # everyone out; promotion of others is fine.
        raise ForbiddenError("You cannot remove your own admin role.")
    old_role = user.role
    target = actor_label(user)
    user.role = body.role
    await audit_repo.add_audit_entry(
        db,
        study_id=None,
        action="admin_set_role",
        old_value=f"{target}: {old_role}",
        new_value=f"{target} → {body.role}",
        actor_id=admin.id,
        curator=actor_label(admin),
    )
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/users/{user_id}/approve-admin", response_model=UserOut)
async def approve_admin_request(
    user_id: int,
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Approve a pending admin-access request: promote the user to admin."""
    user = await users_repo.get_by_id(db, user_id)
    if not user:
        raise NotFoundError("User not found.")
    user.role = "admin"
    user.approved = True
    user.admin_requested = False
    await audit_repo.add_audit_entry(
        db,
        study_id=None,
        action="admin_approve_request",
        new_value=f"{actor_label(user)} → admin",
        actor_id=admin.id,
        curator=actor_label(admin),
    )
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/users/{user_id}/reject-admin", response_model=UserOut)
async def reject_admin_request(
    user_id: int,
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Reject a pending admin-access request: clear the flag, keep curator role."""
    user = await users_repo.get_by_id(db, user_id)
    if not user:
        raise NotFoundError("User not found.")
    user.admin_requested = False
    await audit_repo.add_audit_entry(
        db,
        study_id=None,
        action="admin_reject_request",
        new_value=f"{actor_label(user)} request denied",
        actor_id=admin.id,
        curator=actor_label(admin),
    )
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/users/{user_id}/approve", response_model=UserOut)
async def approve_account(
    user_id: int,
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Approve a pending (untrusted-domain) account so it can sign in."""
    user = await users_repo.get_by_id(db, user_id)
    if not user:
        raise NotFoundError("User not found.")
    user.approved = True
    await audit_repo.add_audit_entry(
        db,
        study_id=None,
        action="admin_approve_account",
        new_value=f"{actor_label(user)} approved",
        actor_id=admin.id,
        curator=actor_label(admin),
    )
    await db.commit()
    await db.refresh(user)
    await send_account_approved_email(to=user.email, name=user.name)
    return UserOut.model_validate(user)


@router.post("/users/{user_id}/reject", response_model=UserOut)
async def reject_account(
    user_id: int,
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Reject a pending account: deactivate it and end any sessions."""
    user = await users_repo.get_by_id(db, user_id)
    if not user:
        raise NotFoundError("User not found.")
    if user.id == admin.id:
        raise ForbiddenError("You cannot reject your own account.")
    user.is_active = False
    await sessions_repo.revoke_all_for_user(db, user_id)
    await audit_repo.add_audit_entry(
        db,
        study_id=None,
        action="admin_reject_account",
        new_value=f"{actor_label(user)} rejected",
        actor_id=admin.id,
        curator=actor_label(admin),
    )
    await db.commit()
    await db.refresh(user)
    await send_account_rejected_email(to=user.email, name=user.name)
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}/active", response_model=UserOut)
async def set_active(
    user_id: int,
    body: ActiveUpdate,
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    user = await users_repo.get_by_id(db, user_id)
    if not user:
        raise NotFoundError("User not found.")
    if user.id == admin.id and not body.is_active:
        raise ForbiddenError("You cannot disable your own account.")
    user.is_active = body.is_active
    if not body.is_active:
        # Disabling an account also ends all of its sessions.
        await sessions_repo.revoke_all_for_user(db, user_id)
    await audit_repo.add_audit_entry(
        db,
        study_id=None,
        action="admin_set_active",
        new_value=f"{actor_label(user)}: {'enabled' if body.is_active else 'disabled'}",
        actor_id=admin.id,
        curator=actor_label(admin),
    )
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/users/{user_id}/logout", status_code=204)
async def force_logout(
    user_id: int,
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Revoke every active session for a user (force sign-out everywhere)."""
    user = await users_repo.get_by_id(db, user_id)
    if not user:
        raise NotFoundError("User not found.")
    await sessions_repo.revoke_all_for_user(db, user_id)
    await audit_repo.add_audit_entry(
        db,
        study_id=None,
        action="admin_force_logout",
        new_value=actor_label(user),
        actor_id=admin.id,
        curator=actor_label(admin),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Schema versioning (U9)
# ---------------------------------------------------------------------------
@router.get("/schema-versions")
async def list_schema_versions(
    target_schema: str | None = None,
    _admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await schema_repo.list_versions(db, target_schema)


@router.post("/schema-versions", status_code=201)
async def upload_schema_version(
    label: str,
    target_schema: str,
    file: UploadFile = File(...),
    promote: bool = False,
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Upload a new curated-fields CSV as a new version of a target schema
    (never an overwrite). Optionally promote it to that target's current in the
    same call."""
    from app.engine_adapter import _schema_registry

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="A .csv file is required.")
    if not _schema_registry.is_valid(target_schema):
        raise HTTPException(
            status_code=400, detail=f"Unknown target schema '{target_schema}'."
        )
    if await schema_repo.get_by_label(db, target_schema, label):
        raise HTTPException(
            status_code=409,
            detail=f"Version '{label}' already exists for '{target_schema}'.",
        )

    SCHEMA_STORE.mkdir(parents=True, exist_ok=True)
    save_path = _new_schema_upload_path()
    with open(save_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    version = await schema_repo.create_version(
        db,
        label=label,
        source_path=str(save_path),
        target_schema=target_schema,
        make_current=promote,
    )
    await audit_repo.add_audit_entry(
        db,
        study_id=None,
        action="schema_version_upload",
        new_value=f"{target_schema}/{label}{' (promoted)' if promote else ''}",
        actor_id=admin.id,
        curator=actor_label(admin),
    )
    await db.commit()
    return {
        "id": version.id,
        "target_schema": version.target_schema,
        "label": version.label,
        "is_current": version.is_current,
    }


@router.get("/schema-aliases")
async def get_schema_aliases(_admin: User = Depends(require_role("admin"))) -> dict:
    """Status of the current column-name alias dictionary."""
    if not ALIAS_FILE.exists():
        return {"present": False, "alias_count": 0, "field_count": 0}
    import pandas as pd

    df = pd.read_csv(ALIAS_FILE)
    return {
        "present": True,
        "alias_count": int(len(df)),
        "field_count": int(df["field_name"].nunique()) if "field_name" in df else 0,
    }


@router.post("/schema-aliases", status_code=201)
async def upload_schema_aliases(
    file: UploadFile = File(...),
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Upload a column-name alias dictionary as **two columns**: the canonical
    field and a comma- (or pipe-) separated list of aliases. Converted to the
    engine's long ``source,field_name`` format and applied by the schema mapper
    on the next harmonize. Replaces any existing alias dictionary."""
    if not file.filename or not file.filename.lower().endswith((".csv", ".tsv", ".txt")):
        raise HTTPException(status_code=400, detail="A .csv file is required.")

    import pandas as pd

    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse CSV: {exc}")
    if df.shape[1] < 2:
        raise HTTPException(status_code=422, detail="Expected two columns: field, aliases.")

    field_col, alias_col = df.columns[0], df.columns[1]
    rows: list[tuple[str, str]] = []
    for _, r in df.iterrows():
        field = str(r[field_col]).strip()
        if not field or field.lower() == "nan":
            continue
        for alias in re.split(r"[,|;]", str(r[alias_col] or "")):
            alias = alias.strip()
            if alias and alias.lower() != "nan":
                rows.append((alias, field))
    if not rows:
        raise HTTPException(status_code=422, detail="No aliases found in the file.")

    ALIAS_STORE.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame(rows, columns=["source", "field_name"]).drop_duplicates()
    out.to_csv(ALIAS_FILE, index=False)

    from app.engine_adapter import schema_dicts

    schema_dicts._invalidate()  # rebuild merged dict + engine on next harmonize
    await audit_repo.add_audit_entry(
        db, study_id=None, action="schema_alias_upload",
        new_value=f"{len(out)} aliases / {out['field_name'].nunique()} fields",
        actor_id=admin.id, curator=actor_label(admin),
    )
    await db.commit()
    return {
        "present": True,
        "alias_count": int(len(out)),
        "field_count": int(out["field_name"].nunique()),
    }


@router.get("/schema-fields")
async def list_schema_fields(_admin: User = Depends(require_role("admin"))) -> dict:
    """Valid target field names for the active schema (for alias validation)."""
    from app.engine_adapter import schema_dicts

    return {"fields": schema_dicts.schema_field_names()}


@router.get("/schema-aliases/entries")
async def list_alias_entries(
    q: str | None = None,
    limit: int = 500,
    _admin: User = Depends(require_role("admin")),
) -> dict:
    """Search the merged alias dictionary (built-in + admin). Built-in rows are
    read-only; admin rows can be removed."""
    from app.engine_adapter import schema_dicts

    return schema_dicts.alias_entries(q, min(max(limit, 1), 2000))


class _AliasEntry(BaseModel):
    source: str
    field_name: str


@router.post("/schema-aliases/entry", status_code=201)
async def add_alias_entry(
    body: _AliasEntry,
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manually add one alias (nickname → canonical field)."""
    from app.engine_adapter import schema_dicts

    try:
        schema_dicts.add_alias(body.source, body.field_name)
    except schema_dicts.AliasExists as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await audit_repo.add_audit_entry(
        db, study_id=None, action="schema_alias_add",
        new_value=f"{body.source} -> {body.field_name}",
        actor_id=admin.id, curator=actor_label(admin),
    )
    await db.commit()
    return {"ok": True}


@router.get("/schema-aliases/export")
async def export_alias_dict(
    scope: str = "merged",
    _admin: User = Depends(require_role("admin")),
):
    """Download the alias dictionary as CSV. ``scope=merged`` (built-in + admin)
    or ``scope=custom`` (admin-added only)."""
    from fastapi import Response

    from app.engine_adapter import schema_dicts

    scope = scope if scope in ("merged", "custom") else "merged"
    csv_text = schema_dicts.export_csv(scope)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="aliases_{scope}.csv"'},
    )


@router.delete("/schema-aliases/entry")
async def delete_alias_entry(
    source: str,
    field_name: str,
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Remove one admin alias (built-ins cannot be removed)."""
    from app.engine_adapter import schema_dicts

    if not schema_dicts.remove_alias(source, field_name):
        raise HTTPException(
            status_code=404,
            detail="Alias not found in the admin layer (built-ins can't be removed).",
        )
    await audit_repo.add_audit_entry(
        db, study_id=None, action="schema_alias_remove",
        new_value=f"{source} -> {field_name}",
        actor_id=admin.id, curator=actor_label(admin),
    )
    await db.commit()
    return {"ok": True}


@router.post("/schema-versions/{version_id}/promote")
async def promote_schema_version(
    version_id: int,
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Make a schema version current. New studies use it; existing studies stay
    pinned to whatever they were harmonized against."""
    version = await schema_repo.promote(db, version_id)
    if not version:
        raise NotFoundError("Schema version not found.")
    await audit_repo.add_audit_entry(
        db,
        study_id=None,
        action="schema_version_promote",
        new_value=version.label,
        actor_id=admin.id,
        curator=actor_label(admin),
    )
    await db.commit()
    return {"id": version.id, "label": version.label, "is_current": True}


@router.get("/schema-versions/diff")
async def diff_schema_versions(
    from_id: int,
    to_id: int,
    _admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Schema-vs-schema diff (G6, layer A): what changed in the curated-fields
    dictionary between two versions — fields added/removed and fields whose
    allowed-value vocabulary changed. Read-only; does not affect any study."""
    from app.services import schema_diff

    old = await db.get(SchemaVersion, from_id)
    new = await db.get(SchemaVersion, to_id)
    if not old or not new:
        raise NotFoundError("Schema version not found.")
    if not old.source_path or not Path(old.source_path).exists():
        raise HTTPException(status_code=404, detail=f"Source CSV missing for version '{old.label}'.")
    if not new.source_path or not Path(new.source_path).exists():
        raise HTTPException(status_code=404, detail=f"Source CSV missing for version '{new.label}'.")

    result = schema_diff.diff_csv_files(old.source_path, new.source_path)
    return {
        "from": {"id": old.id, "label": old.label},
        "to": {"id": new.id, "label": new.label},
        **result,
    }


# ── Two-layer curation KB promotion (ADR-0002, Q10 two-stage approval) ────────
class PromoteRequest(BaseModel):
    kind: str          # 'schema' | 'ontology'
    source_key: str
    decision: str      # 'accept' | 'reject'
    target_field: str | None = None
    target_term: str | None = None
    target_id: str | None = None


class ReviewLearnedRequest(BaseModel):
    action: Literal["promote", "dismiss"]
    candidates: list[PromoteRequest]


class UnpromoteLearnedRequest(BaseModel):
    ids: list[int]


@router.get("/learned-decisions/candidates")
async def learned_promotion_candidates(
    min_support: int = 1,
    _admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Promotion queue: personal decisions with agreement analytics (distinct
    curators, total support), excluding entries already promoted to shared."""
    candidates = await ld_repo.promotion_candidates(db, min_support=min_support)
    return {"count": len(candidates), "candidates": candidates}


@router.get("/learned-decisions/shared")
async def shared_learned_decisions(
    _admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    shared = await ld_repo.list_shared(db)
    return {"count": len(shared), "shared": shared}


@router.post("/learned-decisions/promote")
async def promote_learned_decision(
    body: PromoteRequest,
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Promote a personal decision to the shared layer so it applies for every
    curator. Personal rows are left intact and keep overriding the shared
    baseline for their owner (ADR-0002 precedence)."""
    if body.kind not in ("schema", "ontology") or body.decision not in ("accept", "reject"):
        raise HTTPException(status_code=422, detail="Invalid kind or decision.")
    row = await ld_repo.promote(
        db, kind=body.kind, source_key=body.source_key, decision=body.decision,
        admin_id=admin.id, target_field=body.target_field,
        target_term=body.target_term, target_id=body.target_id,
    )
    await audit_repo.add_audit_entry(
        db, study_id=None, action="kb_promote",
        new_value=f"{body.kind}:{body.source_key}",
        actor_id=admin.id, curator=actor_label(admin),
    )
    await db.commit()
    return {"promoted": row}


@router.post("/learned-decisions/review")
async def review_learned_decisions(
    body: ReviewLearnedRequest,
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not body.candidates or len(body.candidates) > 100:
        raise HTTPException(status_code=422, detail="Select between 1 and 100 candidates.")

    reviewed = []
    for candidate in body.candidates:
        if candidate.kind not in ("schema", "ontology") or candidate.decision not in ("accept", "reject"):
            raise HTTPException(status_code=422, detail="Invalid kind or decision.")
        values = candidate.model_dump()
        if body.action == "promote":
            row = await ld_repo.promote(db, admin_id=admin.id, **values)
        else:
            row = await ld_repo.dismiss(db, admin_id=admin.id, **values)
        reviewed.append(row)
        await audit_repo.add_audit_entry(
            db, study_id=None, action=f"kb_{body.action}",
            new_value=f"{candidate.kind}:{candidate.source_key}:{candidate.decision}",
            actor_id=admin.id, curator=actor_label(admin),
        )

    await db.commit()
    return {"action": body.action, "count": len(reviewed), "reviewed": reviewed}


@router.post("/learned-decisions/unpromote")
async def unpromote_learned_decisions(
    body: UnpromoteLearnedRequest,
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    ids = list(dict.fromkeys(body.ids))
    if not ids or len(ids) > 100:
        raise HTTPException(status_code=422, detail="Select between 1 and 100 promoted decisions.")

    removed = await ld_repo.unpromote(db, ids)
    for row in removed:
        await audit_repo.add_audit_entry(
            db, study_id=None, action="kb_unpromote",
            new_value=f"{row['kind']}:{row['source_key']}",
            actor_id=admin.id, curator=actor_label(admin),
        )
    await db.commit()
    return {"count": len(removed), "unpromoted": removed}
