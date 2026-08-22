"""Real-engine ontology value mapping (F-11, app side).

Routes value→ontology mapping through the upstream ``OntoMapEngine`` for the
engine's first-class categories, falling back to the curated dictionary
otherwise. Opt-in via ``ONTOLOGY_ENGINE=1``. The engine also registers
``("phenotype", "efo")``, but no field in the supported target schemas is a
phenotype term field, so nothing routes there yet. Only this module may touch
the ontology engine.
"""

from __future__ import annotations

import logging
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _auto_accept_threshold() -> float:
    """Confidence at/above which a mapping is auto-accepted (env-tunable per the
    spec's auto-accept / flag-for-review bands; ``AUTO_ACCEPT_THRESHOLD``)."""
    try:
        from app.core.settings import settings

        return float(settings.auto_accept_threshold)
    except Exception:  # noqa: BLE001 — never fail mapping over a config read
        return 0.9

# Dashboard field name (lower) → engine ontology (category, source), limited to
# the engine's first-class tuples; anything else uses the dictionary fallback.
# Excluded on purpose: GDC ``treatment_or_therapy`` (yes/no/unknown) and
# ``morphology`` (ICD-O codes such as 8000/0) are not term vocabularies.
FIELD_ONTOLOGY: dict[str, tuple[str, str]] = {
    "disease": ("disease", "ncit"),
    "target_condition": ("disease", "ncit"),
    "cancer_type": ("disease", "ncit"),
    "primary_diagnosis": ("disease", "ncit"),
    "primary_disease": ("disease", "ncit"),
    "disease_type": ("disease", "ncit"),
    "body_site": ("bodysite", "uberon"),
    "primary_site": ("bodysite", "uberon"),
    "tissue_or_organ_of_origin": ("bodysite", "uberon"),
    "site_of_resection_or_biopsy": ("bodysite", "uberon"),
    "biospecimen_anatomic_site": ("bodysite", "uberon"),
    "treatment": ("treatment", "ncit"),
    "treatment_name": ("treatment", "ncit"),
    "treatment_type": ("treatment", "ncit"),
    "therapeutic_agents": ("treatment", "ncit"),
}


def is_ontology_field(field: str | None) -> bool:
    """True when a curated field routes to a first-class ontology (NCIt/UBERON)."""
    return bool(field) and field.strip().lower() in FIELD_ONTOLOGY


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


def _data_dir() -> Path:
    """Where the engine reads its corpora — mirrors ``_ensure_upstream_data_dir``
    (``$METAHARMONIZER_DATA_DIR`` else the dashboard-owned ``backend/data``)."""
    env = os.environ.get("METAHARMONIZER_DATA_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "data"


@lru_cache(maxsize=8)
def _corpus_label_to_id(category: str, source: str) -> dict[str, str]:
    """Load the ``label -> obo_id`` map for a corpus.

    ``OntoMapEngine.run()`` returns only the matched *label* (``match1``), never
    the ontology code — but every ``match1`` is a row from this corpus, so we can
    recover the code by exact label. Returns ``{}`` (graceful degrade to a
    code-less row) if the corpus can't be read.
    """
    path = _data_dir() / "corpus" / "retrieved_ontologies" / f"{source}_{category}_corpus.csv"
    try:
        df = pd.read_csv(path, usecols=["label", "obo_id"])
    except Exception as exc:  # noqa: BLE001 — missing/renamed corpus -> no codes, not a crash
        logger.warning("ontology code lookup unavailable (%s): %s", path, exc)
        return {}
    mapping: dict[str, str] = {}
    for label, obo in zip(df["label"], df["obo_id"]):
        if not isinstance(label, str):
            continue
        key = label.strip().lower()
        code = "" if obo is None else str(obo).strip()
        if key and code and key not in mapping:  # first-wins for stable output
            mapping[key] = code
    return mapping


def _normalize_engine_rows(
    field_name: str,
    result: "pd.DataFrame",
    category: str | None = None,
    source: str | None = None,
) -> list[dict[str, Any]]:
    """Map an ``OntoMapEngine.run()`` frame to our ontology DTO rows.

    Defensive about column names so an upstream rename degrades to a
    lower-confidence row rather than crashing. When the engine supplies a label
    but no code (its normal behaviour — the output frame has no id column) and
    ``category``/``source`` are known, the code is recovered from the corpus.
    """
    rows: list[dict[str, Any]] = []
    records = result.to_dict(orient="records") if result is not None else []
    label_to_id: dict[str, str] | None = None
    for raw in records:
        query = raw.get("query")
        if query is None:
            continue
        term = raw.get("match1")
        term_missing = term is None or (isinstance(term, float) and math.isnan(term))
        ont_id = (
            raw.get("match1_id")
            or raw.get("match1_obo_id")
            or raw.get("obo_id")
            or None
        )
        # Engine frames carry no code column; recover it from the corpus the
        # match came from. Only load the map when a row actually needs it.
        if ont_id is None and not term_missing and category and source:
            if label_to_id is None:
                label_to_id = _corpus_label_to_id(category, source)
            ont_id = label_to_id.get(str(term).strip().lower())
        score = _to_score(raw.get("match1_score"))
        rows.append(
            {
                "field_name": field_name,
                "raw_value": str(query),
                "ontology_term": None if term_missing else str(term),
                "ontology_id": None if ont_id is None else str(ont_id),
                "confidence_score": round(score, 4),
                "status": "accepted" if score >= _auto_accept_threshold() else "pending",
            }
        )
    return rows


def map_values_via_engine(
    pkg: Any,
    raw_df: "pd.DataFrame",
    schema_mappings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], set[str]]:
    """Map supported fields' values through ``OntoMapEngine``.

    Returns ``(rows, handled_fields)`` — the ontology rows and the set of field
    names the engine covered, so the caller can fall back to the dictionary for
    the rest. A per-category failure is logged and left to the fallback.
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
        rows.extend(_normalize_engine_rows(field_name, result, category, source))
        handled.add(field_name)
    return rows, handled
