"""
MetaHarmonizer Dashboard — Pydantic Models

Request/response schemas for all API endpoints.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Study
# ---------------------------------------------------------------------------

class StudyOut(BaseModel):
    id: str
    name: str
    upload_date: str
    status: str
    file_path: Optional[str] = None
    row_count: Optional[int] = None
    column_count: Optional[int] = None


class StudySummary(BaseModel):
    id: str
    name: str
    status: str
    upload_date: str
    row_count: Optional[int] = None
    column_count: Optional[int] = None
    total_mappings: int = 0
    accepted_count: int = 0
    pending_count: int = 0
    rejected_count: int = 0


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------

class AlternativeMatch(BaseModel):
    field: str
    score: float
    method: Optional[str] = None


class MappingOut(BaseModel):
    id: int
    study_id: str
    raw_column: str
    matched_field: Optional[str] = None
    confidence_score: Optional[float] = None
    stage: Optional[str] = None
    method: Optional[str] = None
    alternatives: list[AlternativeMatch] = []
    status: str = "pending"
    curator_field: Optional[str] = None
    curator_note: Optional[str] = None
    reviewed_at: Optional[str] = None
    reviewed_by: Optional[str] = None


class MappingEditRequest(BaseModel):
    new_field: str
    note: str = ""


class BatchUpdateRequest(BaseModel):
    mapping_ids: list[int]
    action: str = Field(..., pattern="^(accepted|rejected)$")


class BatchUpdateResponse(BaseModel):
    updated: int
    action: str


# ---------------------------------------------------------------------------
# Ontology
# ---------------------------------------------------------------------------

class OntologyMappingOut(BaseModel):
    id: int
    study_id: str
    field_name: str
    raw_value: str
    ontology_term: Optional[str] = None
    ontology_id: Optional[str] = None
    confidence_score: Optional[float] = None
    status: str = "pending"
    curator_term: Optional[str] = None
    curator_id: Optional[str] = None
    reviewed_at: Optional[str] = None
    reviewed_by: Optional[str] = None


class OntologyEditRequest(BaseModel):
    new_term: str
    new_id: Optional[str] = None
    note: str = ""


class OntologySearchResult(BaseModel):
    term: str
    ontology_id: str
    ontology: str
    score: float


# ---------------------------------------------------------------------------
# Quality / Analytics
# ---------------------------------------------------------------------------

class StageBreakdown(BaseModel):
    stage: str
    count: int
    percentage: float


class ConfidenceBucket(BaseModel):
    bucket: str
    min_val: float
    max_val: float
    count: int


class QualityMetrics(BaseModel):
    study_id: str
    total_columns: int
    mapped_columns: int
    unmapped_columns: int
    avg_confidence: float
    auto_accepted: int
    pending_review: int
    rejected: int
    new_field_suggestions: int
    stage_breakdown: list[StageBreakdown]
    confidence_distribution: list[ConfidenceBucket]


# ---------------------------------------------------------------------------
# Harmonization Job
# ---------------------------------------------------------------------------

class HarmonizeResponse(BaseModel):
    job_id: str
    status: str
    study_name: str
    row_count: int
    column_count: int
    message: str


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class ExportInfo(BaseModel):
    format: str
    filename: str
    rows: int
    columns: int


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

class AuditEntry(BaseModel):
    id: int
    study_id: Optional[str] = None
    action: str
    mapping_id: Optional[int] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    curator: Optional[str] = None
    timestamp: str
