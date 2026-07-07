"""Ontology router: search/browse ontology terms (NCIT, UBERON, OHMI), return a
study's ontology mappings, and apply curator overrides."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from rapidfuzz import fuzz, process
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import actor_label as _actor_label, require_role
from app.db.session import get_db
from app.models import OntologyEditRequest, OntologyMappingOut, OntologySearchResult
from app.repositories import audit as audit_repo
from app.repositories import learned_decisions as ld_repo
from app.repositories import ontology as ontology_repo
from app.repositories import studies as studies_repo
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
            "ontology_id": ont_id or "NCIT:unknown",
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
async def get_ontology_mappings(study_id: str, db: AsyncSession = Depends(get_db)):
    """Get all ontology value mappings for a study."""
    study = await studies_repo.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    return await ontology_repo.get_ontology_mappings(db, study_id)


def _best_index_match(value: str) -> tuple[dict, float] | None:
    """Return (index_entry, score 0..1) for the best ontology match of ``value``,
    or None.

    Uses the same in-memory index as /search but guards against a common
    false positive: ``partial_ratio`` treats a short value as a perfect match
    when it's merely a *substring of a longer word* (e.g. "no" inside
    "ade**no**ma"). We therefore only accept a hit when the normalized value
    appears as a whole token (word boundary) in the matched entry — which keeps
    legitimate abbreviations that are real tokens (e.g. "crc" in the entry
    "colorectal cancer crc") while rejecting the substring noise.
    """
    q = value.lower().strip()
    if not q or not _SEARCH_INDEX:
        return None
    keys = [c["search_key"] for c in _SEARCH_INDEX]
    hit = process.extractOne(q, keys, scorer=fuzz.partial_ratio)
    if not hit:
        return None
    _key, score, idx = hit
    entry = _SEARCH_INDEX[idx]
    # Token-boundary guard against substring-of-word false positives.
    if not re.search(rf"\b{re.escape(q)}\b", entry["search_key"]):
        return None
    return entry, score / 100.0


def _is_term_like(value: str) -> bool:
    """Skip pure numbers, identifiers, and over-long free text so we only
    suggest for values that plausibly map to a controlled-vocabulary term."""
    v = value.strip()
    if not (2 <= len(v) <= 40):
        return False
    if not re.search(r"[A-Za-z]", v):
        return False
    if re.fullmatch(r"\d+(\.\d+)?", v):
        return False
    if re.fullmatch(r"[A-Za-z]{1,4}\d{3,}", v):  # e.g. MG100208
        return False
    return True


@router.post("/suggest/{study_id}")
async def suggest_ontology_terms(
    study_id: str,
    threshold: float = Query(default=0.85, ge=0.0, le=1.0),
    _curator=Depends(require_role("curator")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Batch-suggest ontology terms for a study's *unmatched* values in ONE call.

    For every distinct term-like raw value that the engine left without an
    ontology term, search the in-memory ontology index and, when the best hit
    clears ``threshold``, return it keyed by mapping id. Computing this
    server-side avoids the client firing one HTTP request per value (which both
    hammers the rate limiter and is an N+1)."""
    study = await studies_repo.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    rows = await ontology_repo.get_ontology_mappings(db, study_id)

    # Distinct term-like raw values among unmatched rows → best index match once.
    distinct: dict[str, list[int]] = {}
    for r in rows:
        term = r.get("curator_term") or r.get("ontology_term")
        if term:
            continue  # already matched
        raw = str(r.get("raw_value", ""))
        if not _is_term_like(raw):
            continue
        distinct.setdefault(raw.lower().strip(), []).append(r["id"])

    suggestions: dict[str, dict] = {}
    cache: dict[str, tuple[dict, float] | None] = {}
    for value_key, ids in distinct.items():
        if value_key not in cache:
            cache[value_key] = _best_index_match(value_key)
        match = cache[value_key]
        if not match:
            continue
        entry, score = match
        if score < threshold:
            continue
        for mid in ids:
            suggestions[str(mid)] = {
                "term": entry["term"],
                "ontology_id": entry["ontology_id"],
                "score": round(score, 3),
            }

    return {"study_id": study_id, "count": len(suggestions), "suggestions": suggestions}


@router.post("/mappings/{mapping_id}/accept", response_model=OntologyMappingOut)
async def accept_ontology_mapping(
    mapping_id: int,
    remember: bool = Query(False, description="Remember this decision for the curator's future studies (ADR-0002)."),
    user=Depends(require_role("curator")),
    db: AsyncSession = Depends(get_db),
):
    """Accept the automated ontology term assignment."""
    result = await ontology_repo.update_ontology_mapping(
        db, mapping_id, status="accepted", reviewed_by=user.id
    )
    if not result:
        raise HTTPException(status_code=404, detail="Ontology mapping not found")
    await audit_repo.add_audit_entry(
        db,
        study_id=result["study_id"],
        action="onto_accept",
        mapping_id=mapping_id,
        old_value="pending",
        new_value="accepted",
        actor_id=user.id,
        curator=_actor_label(user),
    )
    if remember and result.get("field_name") and result.get("raw_value"):
        await ld_repo.record_personal(
            db, owner_id=user.id, kind="ontology",
            source_key=ld_repo.ontology_key(result["field_name"], result["raw_value"]),
            decision="accept", target_term=result.get("ontology_term"),
            target_id=result.get("ontology_id"), origin_study_id=result["study_id"],
        )
    await db.commit()
    return result


@router.post("/mappings/{mapping_id}/reject", response_model=OntologyMappingOut)
async def reject_ontology_mapping(
    mapping_id: int,
    user=Depends(require_role("curator")),
    db: AsyncSession = Depends(get_db),
):
    """Reject the automated ontology term assignment."""
    result = await ontology_repo.update_ontology_mapping(
        db, mapping_id, status="rejected", reviewed_by=user.id
    )
    if not result:
        raise HTTPException(status_code=404, detail="Ontology mapping not found")
    await audit_repo.add_audit_entry(
        db,
        study_id=result["study_id"],
        action="onto_reject",
        mapping_id=mapping_id,
        old_value="pending",
        new_value="rejected",
        actor_id=user.id,
        curator=_actor_label(user),
    )
    await db.commit()
    return result


@router.patch("/mappings/{mapping_id}", response_model=OntologyMappingOut)
async def edit_ontology_mapping(
    mapping_id: int,
    body: OntologyEditRequest,
    user=Depends(require_role("curator")),
    db: AsyncSession = Depends(get_db),
):
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

    result = await ontology_repo.update_ontology_mapping(
        db,
        mapping_id,
        status="accepted",
        curator_term=body.new_term,
        curator_id=resolved_id,
        reviewed_by=user.id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Ontology mapping not found")

    await audit_repo.add_audit_entry(
        db,
        study_id=result["study_id"],
        action="onto_edit",
        mapping_id=mapping_id,
        old_value=result.get("ontology_term"),
        new_value=body.new_term,
        actor_id=user.id,
        curator=_actor_label(user),
    )
    if body.remember and result.get("field_name") and result.get("raw_value"):
        await ld_repo.record_personal(
            db, owner_id=user.id, kind="ontology",
            source_key=ld_repo.ontology_key(result["field_name"], result["raw_value"]),
            decision="accept", target_term=body.new_term,
            target_id=resolved_id, origin_study_id=result["study_id"],
        )
    await db.commit()
    return result
