"""
MetaHarmonizer — Export Router

Exports harmonized data in CSV, cBioPortal format, and JSON audit reports.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.deps import current_user, ensure_study_visible, require_role
from app.core.storage import get_storage
from app.db.models import User
from app.repositories import studies as studies_repo
from app.services.exporter import (
    export_all_labeled,
    export_cbioportal,
    export_cbioportal_study,
    export_harmonized_csv,
    export_labeled_dataset,
    export_mapping_report,
    linkml_check,
)

router = APIRouter(prefix="/api/v1/export", tags=["export"])


@router.get("/labeled")
async def export_all_labeled_endpoint(
    format: str = "csv",
    _user: User = Depends(require_role("curator")),
    db: AsyncSession = Depends(get_db),
):
    """Pull the global labeled dataset — every study's curator-confirmed schema
    and ontology mappings as one corpus (G9/U16). ``format=csv`` (default) or
    ``jsonl``. This is the same artifact the nightly job persists.
    """
    fmt = format.lower()
    if fmt not in ("csv", "jsonl"):
        raise HTTPException(status_code=400, detail="format must be 'csv' or 'jsonl'")
    content = await export_all_labeled(db, fmt)
    media = "text/csv" if fmt == "csv" else "application/x-ndjson"
    ext = "csv" if fmt == "csv" else "jsonl"
    return PlainTextResponse(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f"attachment; filename=labeled_all.{ext}"},
    )


async def _load_raw_df(
    db: AsyncSession, study_id: str, user: User, *, mark_export: bool = True
) -> pd.DataFrame:
    """Load the original uploaded CSV for a study (owner-scoped)."""
    study = ensure_study_visible(await studies_repo.get_study(db, study_id), user)

    key = study.get("file_path")
    storage = get_storage()
    if not key or not storage.exists(key):
        raise HTTPException(status_code=404, detail="Original data file not found")

    suffix = Path(key).suffix.lower()
    sep = "\t" if suffix in (".tsv", ".txt") else ","
    # Exporting is the "done" signal — mark the study so it's cleaned up at the
    # next logout. A pre-export validation check passes ``mark_export=False``.
    if mark_export:
        await studies_repo.mark_exported(db, study_id)
    with storage.local(key) as local_csv:
        return pd.read_csv(local_csv, sep=sep, low_memory=False)


@router.get("/{study_id}/harmonized")
async def export_harmonized(
    study_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export harmonized CSV with renamed columns."""
    raw_df = await _load_raw_df(db, study_id, user)
    csv_text = await export_harmonized_csv(db, study_id, raw_df)
    await db.commit()
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={study_id}_harmonized.csv"},
    )


@router.get("/{study_id}/cbioportal")
async def export_cbioportal_format(
    study_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export in cBioPortal clinical data format (tab-separated with header lines)."""
    raw_df = await _load_raw_df(db, study_id, user)
    tsv_text = await export_cbioportal(db, study_id, raw_df)
    await db.commit()
    return PlainTextResponse(
        content=tsv_text,
        media_type="text/tab-separated-values",
        headers={
            "Content-Disposition": f"attachment; filename=data_clinical_{study_id}.txt"
        },
    )


@router.get("/{study_id}/cbioportal-study")
async def export_cbioportal_study_folder(
    study_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export a validateData.py-ready cBioPortal study folder (zip with meta files)."""
    raw_df = await _load_raw_df(db, study_id, user)
    zip_bytes = await export_cbioportal_study(db, study_id, raw_df)
    await db.commit()
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={study_id}_cbioportal_study.zip"
        },
    )


@router.get("/{study_id}/labeled")
async def export_labeled(
    study_id: str,
    format: str = "csv",
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export curator-confirmed mappings as a labeled dataset (G9).

    ``format=csv`` (default) or ``format=jsonl``. Only accepted (human-confirmed)
    schema and ontology mappings are included — a labeled corpus for engine
    retraining, not the raw engine output.
    """
    fmt = format.lower()
    if fmt not in ("csv", "jsonl"):
        raise HTTPException(status_code=400, detail="format must be 'csv' or 'jsonl'")
    raw_df = await _load_raw_df(db, study_id, user)
    content = await export_labeled_dataset(db, study_id, raw_df, fmt)
    await db.commit()
    media = "text/csv" if fmt == "csv" else "application/x-ndjson"
    ext = "csv" if fmt == "csv" else "jsonl"
    return PlainTextResponse(
        content=content,
        media_type=media,
        headers={
            "Content-Disposition": f"attachment; filename={study_id}_labeled.{ext}"
        },
    )


@router.get("/{study_id}/linkml-check")
async def export_linkml_check(
    study_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run the LinkML controlled-vocabulary gate on the harmonized output (G9).

    Returns ``{ok, violations}`` — the checklist-vocabulary half of the export
    gate. Does not mark the study exported (it's a pre-export validation).
    """
    raw_df = await _load_raw_df(db, study_id, user, mark_export=False)
    result = await linkml_check(db, study_id, raw_df)
    return JSONResponse(content=result)


@router.get("/{study_id}/report")
async def export_report(
    study_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export full JSON mapping report / audit trail."""
    ensure_study_visible(await studies_repo.get_study(db, study_id), user)

    await studies_repo.mark_exported(db, study_id)
    report = await export_mapping_report(db, study_id)
    await db.commit()
    return PlainTextResponse(
        content=report,
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename={study_id}_report.json"
        },
    )
