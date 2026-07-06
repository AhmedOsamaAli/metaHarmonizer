"""
MetaHarmonizer — Harmonize Router

Handles file upload, triggers the harmonization pipeline, and returns results.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import actor_label, current_user, require_role
from app.core.queue import enqueue_harmonize
from app.core.settings import settings
from app.core.uploads import check_upload_size
from app.db.session import get_db
from app.models import HarmonizeAccepted, OverviewResponse, StudyOut
from app.repositories import audit as audit_repo
from app.repositories import jobs as jobs_repo
from app.repositories import mappings as mappings_repo
from app.repositories import studies as studies_repo
from app.services.analytics import compute_overview
from app.services.harmonizer import generate_study_id

router = APIRouter(prefix="/api/v1", tags=["harmonize"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "uploads"
CURATED_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "metadata_samples"
    / "curated_meta.csv"
)


@router.post("/harmonize", response_model=HarmonizeAccepted, status_code=202)
async def harmonize_study(
    file: UploadFile = File(...),
    mode: str = Form("both"),
    schema_version_id: int | None = Form(None),
    ontology_columns: str | None = Form(None),
    user=Depends(require_role("curator")),
    db_session: AsyncSession = Depends(get_db),
):
    """Upload a metadata file and enqueue harmonization.

    Returns 202 immediately with a ``job_id``; the heavy pipeline runs off the
    request path (thread/worker) so the API stays responsive under many
    concurrent users. The client follows progress on
    ``/api/v1/ws/jobs/{study_id}``.

    ``mode`` selects which mappers run: ``both`` (default), ``schema`` (column
    → field only), or ``ontology`` (value → ontology only). ``schema_version_id``
    picks which registered target schema to map against (defaults to the current
    one). ``ontology_columns`` is a comma-separated column allow-list that scopes
    the ontology pass; leave it blank to resolve every column.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    mode = (mode or "both").strip().lower()
    if mode not in ("both", "schema", "ontology"):
        raise HTTPException(
            status_code=400,
            detail="Invalid mode. Allowed: 'both', 'schema', 'ontology'.",
        )

    onto_cols = [c.strip() for c in (ontology_columns or "").split(",") if c.strip()]

    allowed = (".csv", ".tsv", ".txt")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {allowed}",
        )

    # Save uploaded file
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    study_id = generate_study_id(file.filename)
    save_path = UPLOAD_DIR / f"{study_id}{suffix}"

    # Stream to disk while enforcing the size cap (spec §6.4) — avoids holding
    # a large upload fully in memory before rejecting it.
    max_bytes = settings.max_upload_mb * 1024 * 1024
    written = 0
    with open(save_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > max_bytes:
                f.close()
                save_path.unlink(missing_ok=True)
                check_upload_size(written, settings.max_upload_mb)  # raises 413
            f.write(chunk)

    # Resolve which target schema to map against: an explicitly-chosen registered
    # version, else the current one, else the bundled curated file. The study is
    # stamped with the resolved version for reproducibility.
    from app.repositories import schema_versions as schema_repo

    if schema_version_id is not None:
        chosen_schema = await schema_repo.get_by_id(db_session, schema_version_id)
        if chosen_schema is None:
            save_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=404,
                detail=f"Schema version {schema_version_id} not found.",
            )
    else:
        chosen_schema = await schema_repo.get_current(db_session)

    curated_path = Path(chosen_schema.source_path) if chosen_schema else CURATED_PATH
    if not curated_path.exists():
        save_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail="Curated reference file not found. Place curated_meta.csv in metadata_samples/.",
        )

    # Quick shape read for the study record (cheap; the engine work is deferred).
    sep = "\t" if suffix in (".tsv", ".txt") else ","
    try:
        shape_df = pd.read_csv(save_path, sep=sep, nrows=None, low_memory=False)
    except Exception as exc:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Failed to parse file: {exc}")

    # Optional row ceiling (public-facing instances cap study size).
    if settings.max_upload_rows and len(shape_df) > settings.max_upload_rows:
        save_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=413,
            detail=(
                f"File has {len(shape_df)} rows, exceeding the limit of "
                f"{settings.max_upload_rows}. Contact the operator for bulk access."
            ),
        )

    study_name = Path(file.filename).stem
    await studies_repo.create_study(
        db_session,
        study_id=study_id,
        name=study_name,
        file_path=str(save_path),
        row_count=len(shape_df),
        column_count=len(shape_df.columns),
        owner_id=getattr(user, "id", None),
        schema_version_id=chosen_schema.id if chosen_schema else None,
    )
    await studies_repo.update_status(db_session, study_id, "queued")

    # Record the job and enqueue it (inline thread in dev, arq workers in prod).
    job = await jobs_repo.create_job(db_session, study_id=study_id, kind="harmonize")
    await db_session.commit()
    job_id = job.id

    await enqueue_harmonize(
        job_id=job_id,
        study_id=study_id,
        file_path=str(save_path),
        suffix=suffix,
        curated_path=str(curated_path),
        owner_id=getattr(user, "id", None),
        mode=mode,
        ontology_columns=onto_cols or None,
    )

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
    user=Depends(require_role("curator")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List the registered target schemas a curator can map an upload against.

    Read-only and curator-accessible (the admin equivalent under ``/admin`` also
    allows uploading new versions). Powers the per-upload schema picker."""
    from app.repositories import schema_versions as schema_repo

    return await schema_repo.list_versions(db)


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
async def list_studies(user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    """List the caller's own *active* studies (completed ones are filed away and
    excluded). Studies are private per-user; admin oversight is the audit feed,
    not seeing others' studies."""
    return await studies_repo.list_studies(
        db, owner_id=getattr(user, "id", None), include_completed=False
    )


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Portfolio-wide harmonization summary for the home dashboard, scoped to
    the caller's own studies."""
    return await compute_overview(db, owner_id=getattr(user, "id", None))


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
    user=Depends(require_role("curator")),
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
    user=Depends(require_role("curator")),
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
