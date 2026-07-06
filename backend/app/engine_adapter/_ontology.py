"""Real-engine ontology value mapping (F-11, app side).

Routes value→ontology mapping through the upstream ``OntoMapEngine`` (FAISS +
SQLite over the ontology corpus) for the categories the engine ships as
first-class today, and falls back to the dashboard's curated dictionary for
everything else (or when the engine corpus / API key isn't available).

Boundary: this module lives under ``engine_adapter/`` and is the only place
allowed to touch the upstream ontology engine. It uses the engine's *public*
API (no fork), so EFO / HANCESTRO are deliberately NOT added here — those need
engine-team support (a registry root for EFO, a new category for HANCESTRO).

Opt-in: the engine path runs only when ``ONTOLOGY_ENGINE=1``. Default keeps the
deterministic dictionary behaviour so existing deployments are unchanged until
the ontology KB is pre-built (needs ``UMLS_API_KEY`` for NCIt / OLS access).
"""

from __future__ import annotations

import logging
import math
import os
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Dashboard field name (lower) → engine ontology (category, source). Only the
# tuples the installed engine ships as first-class are listed; anything else
# falls through to the curated-dictionary path.
FIELD_ONTOLOGY: dict[str, tuple[str, str]] = {
    "disease": ("disease", "ncit"),
    "target_condition": ("disease", "ncit"),
    "body_site": ("bodysite", "uberon"),
    "treatment": ("treatment", "ncit"),
    "treatment_name": ("treatment", "ncit"),
}


def engine_enabled() -> bool:
    """True when the operator has opted into the real ontology engine path."""
    return os.getenv("ONTOLOGY_ENGINE", "0").strip().lower() in {"1", "true", "yes", "on"}


def _to_score(value: Any) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(f) or math.isinf(f):
        return 0.0
    return max(0.0, min(1.0, f))


def _normalize_engine_rows(
    field_name: str, result: "pd.DataFrame"
) -> list[dict[str, Any]]:
    """Map an ``OntoMapEngine.run()`` result frame to our ontology DTO rows.

    Defensive about column names so a minor upstream rename degrades to a
    lower-confidence row rather than crashing (the contract test guards the
    schema-mapping side; ontology output is newer/less pinned).
    """
    rows: list[dict[str, Any]] = []
    records = result.to_dict(orient="records") if result is not None else []
    for raw in records:
        query = raw.get("query")
        if query is None:
            continue
        term = raw.get("match1")
        ont_id = (
            raw.get("match1_id")
            or raw.get("match1_obo_id")
            or raw.get("obo_id")
            or None
        )
        score = _to_score(raw.get("match1_score"))
        term_missing = term is None or (isinstance(term, float) and math.isnan(term))
        rows.append(
            {
                "field_name": field_name,
                "raw_value": str(query),
                "ontology_term": None if term_missing else str(term),
                "ontology_id": None if ont_id is None else str(ont_id),
                "confidence_score": round(score, 4),
                "status": "accepted" if score >= 0.90 else "pending",
            }
        )
    return rows


def map_values_via_engine(
    pkg: Any,
    raw_df: "pd.DataFrame",
    schema_mappings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], set[str]]:
    """Map supported fields' values through ``OntoMapEngine``.

    Returns ``(rows, handled_fields)`` — the ontology rows produced by the
    engine and the set of field names it covered (so the caller can fall back to
    the dictionary for the rest). Any per-category failure is logged and that
    category is left to the fallback (``handled_fields`` excludes it).
    """
    OntoMapEngine = getattr(pkg, "OntoMapEngine", None)
    if OntoMapEngine is None:
        return [], set()

    # Collect unique values per supported field.
    per_field: dict[str, list[str]] = {}
    for m in schema_mappings:
        target = (m.get("curator_field") or m.get("matched_field") or "").strip().lower()
        if target not in FIELD_ONTOLOGY:
            continue
        raw_col = m.get("raw_column")
        if not raw_col or raw_col not in raw_df.columns:
            continue
        values = [str(v) for v in raw_df[raw_col].dropna().unique() if str(v).strip()]
        if values:
            per_field.setdefault(target, []).extend(values)

    rows: list[dict[str, Any]] = []
    handled: set[str] = set()
    for field_name, values in per_field.items():
        category, source = FIELD_ONTOLOGY[field_name]
        uniq = sorted(set(values))
        try:
            # engine >=0.4.0: category -> corpus_category, query -> query_ls,
            # test_or_prod dropped (inferred from ground_truth_map).
            engine = OntoMapEngine(
                corpus_category=category,
                query_ls=uniq,
                ontology_source=source,
                s2_method="sap-bert",
                s2_strategy="st",
            )
            result = engine.run()
        except Exception as exc:  # noqa: BLE001 — fall back on any engine error
            logger.warning(
                "ontology engine failed for field %s (%s/%s): %s; falling back",
                field_name, category, source, exc,
            )
            continue
        rows.extend(_normalize_engine_rows(field_name, result))
        handled.add(field_name)
    return rows, handled
