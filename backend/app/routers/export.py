"""
MetaHarmonizer — Export Router

Exports harmonized data in CSV, cBioPortal format, and JSON audit reports.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app import database as db
from app.services.exporter import (
    export_cbioportal,
    export_harmonized_csv,
    export_mapping_report,
)

router = APIRouter(prefix="/api/v1/export", tags=["export"])


def _load_raw_df(study_id: str) -> pd.DataFrame:
    """Load the original uploaded CSV for a study."""
    study = db.get_study(study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    path = study.get("file_path")
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="Original data file not found")

    suffix = Path(path).suffix.lower()
    sep = "\t" if suffix in (".tsv", ".txt") else ","
    return pd.read_csv(path, sep=sep, low_memory=False)


@router.get("/{study_id}/harmonized")
async def export_harmonized(study_id: str):
    """Export harmonized CSV with renamed columns."""
    raw_df = _load_raw_df(study_id)
    csv_text = export_harmonized_csv(study_id, raw_df)
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={study_id}_harmonized.csv"},
    )


@router.get("/{study_id}/cbioportal")
async def export_cbioportal_format(study_id: str):
    """Export in cBioPortal clinical data format (tab-separated with header lines)."""
    raw_df = _load_raw_df(study_id)
    tsv_text = export_cbioportal(study_id, raw_df)
    return PlainTextResponse(
        content=tsv_text,
        media_type="text/tab-separated-values",
        headers={
            "Content-Disposition": f"attachment; filename=data_clinical_{study_id}.txt"
        },
    )


@router.get("/{study_id}/report")
async def export_report(study_id: str):
    """Export full JSON mapping report / audit trail."""
    study = db.get_study(study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    report = export_mapping_report(study_id)
    return PlainTextResponse(
        content=report,
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename={study_id}_report.json"
        },
    )
