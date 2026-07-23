"""
MetaHarmonizer — Harmonize Router

Handles file upload, triggers the harmonization pipeline, and returns results.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import actor_label, current_user, require_role
from app.core.errors import ServiceUnavailableError
from app.core.queue import enqueue_harmonize, has_capacity
from app.core.settings import settings
from app.core.storage import get_storage
from app.core.uploads import check_upload_size
from app.db.models import User
from app.db.session import get_db
from app.models import HarmonizeAccepted, StudyOut
from app.repositories import audit as audit_repo
from app.repositories import jobs as jobs_repo
from app.repositories import mappings as mappings_repo
from app.repositories import studies as studies_repo
from app.services.harmonizer import generate_study_id

router = APIRouter(prefix="/api/v1", tags=["harmonize"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "uploads"
CURATED_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "metadata_samples"
    / "curated_meta.csv"
)

_ALLOWED_SUFFIXES = (".csv", ".tsv", ".txt")


def _validate_mode(mode: str) -> str:
    mode = (mode or "both").strip().lower()
    if mode not in ("both", "schema", "ontology"):
        raise HTTPException(400, "Invalid mode. Allowed: 'both', 'schema', 'ontology'.")
    return mode


def _validate_suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(400, f"Unsupported file type '{suffix}'. Allowed: {_ALLOWED_SUFFIXES}")
    return suffix


async def _stream_upload(file: UploadFile, save_path: Path, max_bytes: int) -> str:
    """Stream an upload to disk, enforcing the size cap without buffering it all.

    Returns the sha256 of the bytes written (used for double-submit dedup).
    """
    hasher = hashlib.sha256()
    written = 0
    with open(save_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > max_bytes:
                f.close()
                save_path.unlink(missing_ok=True)
                check_upload_size(written, settings.max_upload_mb)  # raises 413
            hasher.update(chunk)
            f.write(chunk)
    return hasher.hexdigest()


async def _resolve_schema(
    db: AsyncSession, schema_version_id: int | None, target_schema: str | None = None
):
    """Resolve the schema version: explicit id, else the chosen target's current,
    else the bundled curated reference."""
    from app.engine_adapter import _schema_registry
    from app.repositories import schema_versions as schema_repo

    if schema_version_id is not None:
        chosen = await schema_repo.get_by_id(db, schema_version_id)
        if chosen is None:
            raise HTTPException(404, f"Schema version {schema_version_id} not found.")
    else:
        key = target_schema or _schema_registry.default_key()
        chosen = await schema_repo.get_current(db, key)
    curated_path = Path(chosen.source_path) if chosen and chosen.source_path else CURATED_PATH
    if not curated_path.exists():
        raise HTTPException(
            500, "Curated reference file not found. Place curated_meta.csv in metadata_samples/."
        )
    return chosen, curated_path


def _read_shape(save_path: Path, suffix: str) -> pd.DataFrame:
    sep = "\t" if suffix in (".tsv", ".txt") else ","
    try:
        return pd.read_csv(save_path, sep=sep, low_memory=False)
    except Exception as exc:
        raise HTTPException(422, f"Failed to parse file: {exc}")


def _enforce_row_cap(shape_df: pd.DataFrame) -> None:
    cap = settings.max_upload_rows
    if cap and len(shape_df) > cap:
        raise HTTPException(
            413,
            f"File has {len(shape_df)} rows, exceeding the limit of {cap}. "
            "Contact the operator for bulk access.",
        )


async def _accepted_for_existing(db: AsyncSession, dup: dict) -> HarmonizeAccepted:
    """202 response pointing at an already in-flight study/job (dedup path)."""
    existing_job = await jobs_repo.latest_for_study(db, dup["id"])
    return HarmonizeAccepted(
        job_id=existing_job.id if existing_job else 0,
        study_id=dup["id"],
        study_name=dup["name"],
        status=dup["status"],
        row_count=dup.get("row_count") or 0,
        column_count=dup.get("column_count") or 0,
        message="This file is already being harmonized.",
    )


@router.post("/harmonize", response_model=HarmonizeAccepted, status_code=202)
async def harmonize_study(
    file: UploadFile = File(...),
    mode: str = Form("both"),
    schema_version_id: int | None = Form(None),
    ontology_columns: str | None = Form(None),
    target_schema: str | None = Form(None),
    user: User = Depends(require_role("curator")),
    db_session: AsyncSession = Depends(get_db),
):
    """Upload a metadata file and enqueue harmonization.

    Returns 202 with a ``job_id``; the pipeline runs off the request path and
    the client follows ``/api/v1/ws/jobs/{study_id}``. ``mode`` is ``both`` /
    ``schema`` / ``ontology``; ``schema_version_id`` picks the target schema
    (default current); ``ontology_columns`` scopes the ontology pass.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    mode = _validate_mode(mode)
    suffix = _validate_suffix(file.filename)
    onto_cols = [c.strip() for c in (ontology_columns or "").split(",") if c.strip()]

    # Validate the curator's chosen target schema (GDC / cBioPortal / cMD / …).
    from app.engine_adapter import _schema_registry

    if target_schema and not _schema_registry.is_valid(target_schema):
        raise HTTPException(400, f"Unknown target schema '{target_schema}'.")

    # Backpressure: refuse before doing any work (upload/parse) when the queue is full.
    if not await has_capacity():
        raise ServiceUnavailableError(
            "The harmonization queue is at capacity. Please retry shortly."
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    study_id = generate_study_id(file.filename)
    save_path = UPLOAD_DIR / f"{study_id}{suffix}"

    content_sha256 = await _stream_upload(
        file, save_path, settings.max_upload_mb * 1024 * 1024
    )
    try:
        chosen_schema, curated_path = await _resolve_schema(
            db_session, schema_version_id, target_schema
        )
        shape_df = _read_shape(save_path, suffix)
        _enforce_row_cap(shape_df)
    except Exception:
        save_path.unlink(missing_ok=True)
        raise

    owner_id = getattr(user, "id", None)

    # Idempotency fast path: if this owner is already harmonizing an identical
    # file, return that in-flight job instead of doing the work twice.
    dup = await studies_repo.find_active_by_content(
        db_session, owner_id=owner_id, content_sha256=content_sha256
    )
    if dup is not None:
        save_path.unlink(missing_ok=True)
        return await _accepted_for_existing(db_session, dup)

    study_name = Path(file.filename).stem
    file_key = f"{study_id}{suffix}"
    # Stamp the KB snapshot in effect so the study's ontology mappings are
    # reproducible against the exact engine + knowledge base that produced them.
    from app.repositories import ontology_snapshots as onto_repo

    current_snapshot = await onto_repo.get_current(db_session)
    try:
        await studies_repo.create_study(
            db_session,
            study_id=study_id,
            name=study_name,
            file_path=file_key,
            row_count=len(shape_df),
            column_count=len(shape_df.columns),
            owner_id=owner_id,
            schema_version_id=chosen_schema.id if chosen_schema else None,
            ontology_snapshot_id=current_snapshot.id if current_snapshot else None,
            content_sha256=content_sha256,
        )
        await studies_repo.update_status(db_session, study_id, "queued")
        # Record the job (inline thread in dev, arq workers in prod).
        job = await jobs_repo.create_job(db_session, study_id=study_id, kind="harmonize")
        await db_session.commit()
    except IntegrityError:
        # Lost a race with a concurrent identical submit — the active-dedup index
        # rejected this insert. Return the winner's in-flight job.
        await db_session.rollback()
        save_path.unlink(missing_ok=True)
        dup = await studies_repo.find_active_by_content(
            db_session, owner_id=owner_id, content_sha256=content_sha256
        )
        if dup is None:
            raise
        return await _accepted_for_existing(db_session, dup)

    job_id = job.id

    # Persist the upload to object storage now that the study row is committed;
    # the DB stores the object key. On a remote backend the local temp is gone.
    storage = get_storage()
    storage.store(file_key, save_path)
    if storage.scheme != "file":
        save_path.unlink(missing_ok=True)

    try:
        await enqueue_harmonize(
            job_id=job_id,
            study_id=study_id,
            file_path=file_key,
            suffix=suffix,
            curated_path=str(curated_path),
            owner_id=owner_id,
            mode=mode,
            ontology_columns=onto_cols or None,
            target_schema=target_schema,
        )
    except Exception as exc:  # noqa: BLE001 — queue unreachable: shed load, don't run in-process
        raise HTTPException(
            status_code=503,
            detail="The job queue is temporarily unavailable. Please retry shortly.",
            headers={"Retry-After": "10"},
        ) from exc

    return HarmonizeAccepted(
        job_id=job_id,
        study_id=study_id,
        study_name=study_name,
        status="queued",
        row_count=len(shape_df),
        column_count=len(shape_df.columns),
        message="Harmonization started.",
    )


@router.get("/schema-versions")
async def list_target_schemas(
    user: User = Depends(require_role("curator")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List the registered target schemas a curator can map an upload against."""
    from app.repositories import schema_versions as schema_repo

    return await schema_repo.list_versions(db)


@router.get("/target-schemas")
async def list_engine_target_schemas(
    user: User = Depends(require_role("curator")),
) -> list[dict]:
    """Target schemas the engine can map into (GDC / cBioPortal / cMD / …), for
    the upload picker. Reads the installed SchemaRegistry artifacts — no engine
    import, so it's cheap even on a cold server."""
    from app.engine_adapter import _schema_registry

    return _schema_registry.available_schemas()


@router.get("/harmonize/{job_id}")
async def get_harmonization_results(job_id: str, db: AsyncSession = Depends(get_db)):
    """Get the schema mapping results for a harmonization job."""
    study = await studies_repo.get_study(db, job_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    mappings = await mappings_repo.get_mappings(db, job_id)
    return {
        "study": study,
        "mappings": mappings,
        "total": len(mappings),
    }


@router.get("/studies", response_model=list[StudyOut])
async def list_studies(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """List the caller's own active studies (completed ones are filed away)."""
    return await studies_repo.list_studies(
        db, owner_id=getattr(user, "id", None), include_completed=False
    )


@router.get("/studies/{study_id}", response_model=StudyOut)
async def get_study(study_id: str, db: AsyncSession = Depends(get_db)):
    """Get study details."""
    study = await studies_repo.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    return study


@router.delete("/studies/{study_id}", status_code=204)
async def delete_study(
    study_id: str,
    user: User = Depends(require_role("curator")),
    db: AsyncSession = Depends(get_db),
):
    """Delete one of the caller's studies (and its mappings/ontology rows)."""
    study = await studies_repo.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    if study.get("owner_id") not in (None, getattr(user, "id", None)):
        raise HTTPException(status_code=403, detail="Not your study")
    await studies_repo.delete_study(db, study_id)
    await audit_repo.add_audit_entry(
        db,
        study_id=study_id,
        action="study_delete",
        new_value=study.get("name"),
        actor_id=user.id,
        curator=actor_label(user),
    )
    await db.commit()


@router.post("/studies/{study_id}/complete", response_model=StudyOut)
async def complete_study(
    study_id: str,
    user: User = Depends(require_role("curator")),
    db: AsyncSession = Depends(get_db),
):
    """Mark a study completed: it's kept (so its work still counts toward the
    dashboard) but filed away — excluded from the work-list pickers and exempt
    from idle-expiry."""
    study = await studies_repo.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    if study.get("owner_id") not in (None, getattr(user, "id", None)):
        raise HTTPException(status_code=403, detail="Not your study")
    result = await studies_repo.mark_completed(db, study_id)
    await audit_repo.add_audit_entry(
        db,
        study_id=study_id,
        action="study_complete",
        new_value=study.get("name"),
        actor_id=user.id,
        curator=actor_label(user),
    )
    await db.commit()
    return result
