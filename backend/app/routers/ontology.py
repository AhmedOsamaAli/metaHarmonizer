"""
MetaHarmonizer — Ontology Router

Search and browse ontology terms (NCIT, UBERON, OHMI).
Also returns ontology mappings for a study and allows curator overrides.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from rapidfuzz import fuzz, process

from app import database as db
from app.models import OntologyEditRequest, OntologyMappingOut, OntologySearchResult
from app.services.harmonizer import ONTOLOGY_MAP, _STATIC_NCIT, _load_field_value_dict

router = APIRouter(prefix="/api/v1/ontology", tags=["ontology"])


# ---------------------------------------------------------------------------
# Build a rich flat search index combining:
#   1. All entries from ONTOLOGY_MAP (curated, with known NCIT IDs)
#   2. All canonical terms in field_value_dict.json (resolved via _STATIC_NCIT)
# ---------------------------------------------------------------------------

def _build_search_index() -> list[dict]:
    seen_terms: set[str] = set()
    index: list[dict] = []

    def _add(term: str, raw: str, ont_id: str | None) -> None:
        key = term.lower()
        if key in seen_terms:
            return
        seen_terms.add(key)
        if not ont_id:
            # Try _STATIC_NCIT
            code = _STATIC_NCIT.get(key)
            if code:
                ont_id = code if ":" in code else f"NCIT:{code}"
        if ont_id:
            prefix = ont_id.split(":")[0] if ":" in ont_id else "NCIT"
        else:
            prefix = "NCIT"
        index.append({
            "term": term,
            "ontology_id": ont_id or f"NCIT:unknown",
            "ontology": prefix,
            "search_key": f"{term} {raw}".lower(),
        })

    # 1. ONTOLOGY_MAP (has curated IDs)
    for _field, _vmap in ONTOLOGY_MAP.items():
        for _raw, (_term, _oid) in _vmap.items():
            _add(_term, _raw, _oid)

    # 2. field_value_dict (broader vocabulary, up to 14 fields × many values)
    fvd = _load_field_value_dict()
    for _field, _values in fvd.items():
        for v in _values:
            _add(v, _field, None)

    return index


_SEARCH_INDEX: list[dict] = _build_search_index()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/search", response_model=list[OntologySearchResult])
async def search_ontology(
    query: str = Query(..., min_length=1),
    ontology: str = Query(default="", description="Filter by ontology prefix: NCIT, UBERON"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Fuzzy-search ontology terms by name, synonym, or ID."""
    q = query.lower()
    candidates = _SEARCH_INDEX
    if ontology:
        candidates = [c for c in candidates if c["ontology"] == ontology.upper()]

    keys = [c["search_key"] for c in candidates]
    if not keys:
        return []

    results = process.extract(q, keys, scorer=fuzz.partial_ratio, limit=limit)
    output = []
    for _match_key, score, idx in results:
        entry = candidates[idx]
        output.append(OntologySearchResult(
            term=entry["term"],
            ontology_id=entry["ontology_id"],
            ontology=entry["ontology"],
            score=round(score / 100, 3),
        ))
    return output


@router.get("/mappings/{study_id}", response_model=list[OntologyMappingOut])
async def get_ontology_mappings(study_id: str):
    """Get all ontology value mappings for a study."""
    study = db.get_study(study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    return db.get_ontology_mappings(study_id)


@router.post("/mappings/{mapping_id}/accept", response_model=OntologyMappingOut)
async def accept_ontology_mapping(mapping_id: int):
    """Accept the automated ontology term assignment."""
    result = db.update_ontology_mapping(mapping_id, status="accepted")
    if not result:
        raise HTTPException(status_code=404, detail="Ontology mapping not found")
    db.add_audit_entry(
        study_id=result["study_id"],
        action="onto_accept",
        mapping_id=mapping_id,
        old_value="pending",
        new_value="accepted",
    )
    return result


@router.post("/mappings/{mapping_id}/reject", response_model=OntologyMappingOut)
async def reject_ontology_mapping(mapping_id: int):
    """Reject the automated ontology term assignment."""
    result = db.update_ontology_mapping(mapping_id, status="rejected")
    if not result:
        raise HTTPException(status_code=404, detail="Ontology mapping not found")
    db.add_audit_entry(
        study_id=result["study_id"],
        action="onto_reject",
        mapping_id=mapping_id,
        old_value="pending",
        new_value="rejected",
    )
    return result


@router.patch("/mappings/{mapping_id}", response_model=OntologyMappingOut)
async def edit_ontology_mapping(mapping_id: int, body: OntologyEditRequest):
    """
    Curator manually overrides an ontology term assignment.

    Provide the correct canonical term name (new_term) and optionally an
    explicit ontology ID (new_id, e.g. 'NCIT:C20197').  If new_id is omitted,
    the endpoint attempts to auto-resolve it from the static NCIT lookup table.
    """
    # Auto-resolve ID from static table if not provided
    resolved_id = body.new_id
    if not resolved_id:
        code = _STATIC_NCIT.get(body.new_term.strip().lower())
        if code:
            resolved_id = code if ":" in code else f"NCIT:{code}"

    result = db.update_ontology_mapping(
        mapping_id,
        status="accepted",
        curator_term=body.new_term,
        curator_id=resolved_id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Ontology mapping not found")

    db.add_audit_entry(
        study_id=result["study_id"],
        action="onto_edit",
        mapping_id=mapping_id,
        old_value=result.get("ontology_term"),
        new_value=body.new_term,
    )
    return result
