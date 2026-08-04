"""Re-run value→ontology mapping for a single column after its schema field
changed in review.

Ontology mappings are first computed at harmonize time from the *engine's
proposed* fields. When a curator edits a column to a different field, the value
codes can become stale — this keeps them consistent:

- moved **into** an ontology-bearing field (disease/body_site/treatment) → add codes,
- moved **out** of one → drop the now-stale codes.

Best-effort: any failure returns zero counts and leaves existing data untouched,
so a schema edit is never blocked by the ontology re-run.
"""
from __future__ import annotations

import logging

import anyio
import pandas as pd

from app.core.storage import get_storage
from app.engine_adapter import get_engine
from app.repositories import ontology as ontology_repo
from app.services.harmonizer import supports_ontology_mapping

logger = logging.getLogger(__name__)


def _column_values(file_key: str, raw_column: str) -> list[str]:
    """Distinct non-empty values of one column, read straight from the upload."""
    sep = "\t" if str(file_key).lower().endswith((".tsv", ".txt")) else ","
    with get_storage().local(file_key) as local_csv:
        series = pd.read_csv(local_csv, sep=sep, usecols=[raw_column], dtype=str)[raw_column]
    return [str(v) for v in series.dropna().unique() if str(v).strip()]


async def rerun_column_ontology(
    db,
    *,
    study_id: str,
    file_key: str | None,
    raw_column: str,
    old_field: str | None,
    new_field: str | None,
) -> dict[str, int]:
    """Re-map one column's values after its field changed. Returns
    ``{"added": n, "removed": m}``. Does not commit — the caller owns the txn."""
    if not supports_ontology_mapping(old_field) and not supports_ontology_mapping(new_field):
        return {"added": 0, "removed": 0}
    if not raw_column or not file_key:
        return {"added": 0, "removed": 0}

    try:
        values = await anyio.to_thread.run_sync(_column_values, file_key, raw_column)
    except Exception as exc:  # noqa: BLE001 — a missing/renamed column must not break the edit
        logger.warning("ontology re-run: could not read column %r: %s", raw_column, exc)
        return {"added": 0, "removed": 0}
    value_set = set(values)
    if not value_set:
        return {"added": 0, "removed": 0}

    # Fresh engine output for the new field (empty when it isn't ontology-bearing).
    new_rows: list[dict] = []
    if supports_ontology_mapping(new_field):
        raw_df = pd.DataFrame({raw_column: values})
        schema_mappings = [
            {"raw_column": raw_column, "matched_field": new_field, "curator_field": new_field}
        ]
        try:
            engine = get_engine()
            new_rows = await anyio.to_thread.run_sync(
                engine.map_values, raw_df, schema_mappings
            )
        except Exception as exc:  # noqa: BLE001 — never let the engine break the edit
            logger.warning("ontology re-run: engine map_values failed: %s", exc)
            new_rows = []

    fields = {f for f in (old_field, new_field) if f}
    removed = await ontology_repo.delete_unreviewed_ontology(db, study_id, fields, value_set)

    # Skip rows the curator already reviewed for the new field (don't clobber decisions).
    existing = (
        await ontology_repo.existing_value_keys(db, study_id, {new_field}, value_set)
        if supports_ontology_mapping(new_field)
        else set()
    )
    fresh = [r for r in new_rows if (r.get("field_name"), r.get("raw_value")) not in existing]
    if fresh:
        await ontology_repo.insert_ontology_mappings(db, study_id, fresh)
    return {"added": len(fresh), "removed": removed}
