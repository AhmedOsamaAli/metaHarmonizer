"""
MetaHarmonizer — Ontology Router

Search and browse ontology terms (NCIT, UBERON, OHMI).
Also returns ontology mappings for a study.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from rapidfuzz import fuzz, process

from app import database as db
from app.models import OntologyMappingOut, OntologySearchResult
from app.services.harmonizer import ONTOLOGY_MAP

router = APIRouter(prefix="/api/v1/ontology", tags=["ontology"])


# Build flat search index from ONTOLOGY_MAP
_SEARCH_INDEX: list[dict] = []
for _field, _vmap in ONTOLOGY_MAP.items():
    for _raw, (_term, _oid) in _vmap.items():
        _SEARCH_INDEX.append(
            {
                "term": _term,
                "ontology_id": _oid,
                "ontology": _oid.split(":")[0] if ":" in _oid else "UNKNOWN",
                "search_key": f"{_term} {_raw} {_oid}".lower(),
            }
        )

# Deduplicate by ontology_id
_seen_ids: set[str] = set()
_UNIQUE_INDEX: list[dict] = []
for entry in _SEARCH_INDEX:
    if entry["ontology_id"] not in _seen_ids:
        _seen_ids.add(entry["ontology_id"])
        _UNIQUE_INDEX.append(entry)


@router.get("/search", response_model=list[OntologySearchResult])
async def search_ontology(
    query: str = Query(..., min_length=1),
    ontology: str = Query(default="", description="Filter by ontology prefix (NCIT, UBERON, OHMI)"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Search ontology terms by name or ID."""
    q = query.lower()

    candidates = _UNIQUE_INDEX
    if ontology:
        candidates = [c for c in candidates if c["ontology"] == ontology.upper()]

    keys = [c["search_key"] for c in candidates]
    if not keys:
        return []

    results = process.extract(q, keys, scorer=fuzz.partial_ratio, limit=limit)

    output = []
    for match_key, score, idx in results:
        entry = candidates[idx]
        output.append(
            OntologySearchResult(
                term=entry["term"],
                ontology_id=entry["ontology_id"],
                ontology=entry["ontology"],
                score=round(score / 100, 3),
            )
        )
    return output


@router.get("/mappings/{study_id}", response_model=list[OntologyMappingOut])
async def get_ontology_mappings(study_id: str):
    """Get all ontology value mappings for a study."""
    study = db.get_study(study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    return db.get_ontology_mappings(study_id)
