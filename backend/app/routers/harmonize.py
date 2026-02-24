"""
MetaHarmonizer — Harmonize Router

Handles file upload, triggers the harmonization pipeline, and returns results.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

logger = logging.getLogger(__name__)

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile

from app import database as db
from app.models import HarmonizeResponse, StudyOut
from app.services.harmonizer import (
    generate_study_id,
    run_ontology_mapping,
    run_schema_mapping,
)

router = APIRouter(prefix="/api/v1", tags=["harmonize"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "uploads"
CURATED_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "metadata_samples"
    / "curated_meta.csv"
)


@router.post("/harmonize", response_model=HarmonizeResponse)
async def harmonize_study(file: UploadFile = File(...)):
    """Upload a clinical metadata file and run the full harmonization pipeline."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

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

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Read data
    sep = "\t" if suffix in (".tsv", ".txt") else ","
    try:
        raw_df = pd.read_csv(save_path, sep=sep, low_memory=False)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse file: {exc}")

    if not CURATED_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail="Curated reference file not found. Place curated_meta.csv in metadata_samples/.",
        )

    curated_df = pd.read_csv(CURATED_PATH, low_memory=False)

    # Create study record
    study_name = Path(file.filename).stem
    db.create_study(
        study_id=study_id,
        name=study_name,
        file_path=str(save_path),
        row_count=len(raw_df),
        column_count=len(raw_df.columns),
    )
    db.update_study_status(study_id, "processing")

    # Run schema mapping pipeline (pass csv_path for real SchemaMapEngine)
    t0 = time.perf_counter()
    schema_results = run_schema_mapping(raw_df, curated_df, csv_path=str(save_path))
    t_schema = time.perf_counter() - t0
    db.insert_mappings(study_id, schema_results)

    # Run ontology value mapping
    t1 = time.perf_counter()
    onto_results = run_ontology_mapping(raw_df, schema_results)
    if onto_results:
        db.insert_ontology_mappings(study_id, onto_results)
    t_onto = time.perf_counter() - t1

    db.update_study_status(study_id, "review")

    total = time.perf_counter() - t0
    logger.info(
        "Pipeline timing: schema=%.1fs  ontology=%.1fs  total=%.1fs",
        t_schema, t_onto, total,
    )

    return HarmonizeResponse(
        job_id=study_id,
        status="review",
        study_name=study_name,
        row_count=len(raw_df),
        column_count=len(raw_df.columns),
        message=f"Harmonization complete. {len(schema_results)} columns processed.",
    )


@router.get("/harmonize/{job_id}")
async def get_harmonization_results(job_id: str):
    """Get the schema mapping results for a harmonization job."""
    study = db.get_study(job_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    mappings = db.get_mappings(job_id)
    return {
        "study": study,
        "mappings": mappings,
        "total": len(mappings),
    }


@router.get("/studies", response_model=list[StudyOut])
async def list_studies():
    """List all harmonized studies."""
    return db.list_studies()


@router.get("/studies/{study_id}", response_model=StudyOut)
async def get_study(study_id: str):
    """Get study details."""
    study = db.get_study(study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    return study
