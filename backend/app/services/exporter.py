"""
MetaHarmonizer Dashboard — Exporter Service

Generates harmonized output files in multiple formats:
- CSV (harmonized metadata)
- cBioPortal clinical data format
- JSON mapping report (audit trail)
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

import pandas as pd

from app import database as db


# ---------------------------------------------------------------------------
# Harmonized CSV
# ---------------------------------------------------------------------------

def export_harmonized_csv(study_id: str, raw_df: pd.DataFrame) -> str:
    """
    Produce a harmonized CSV: rename raw columns to their accepted/curated
    mappings, drop unmapped columns, and return CSV text.
    """
    mappings = db.get_mappings(study_id)

    rename_map: dict[str, str] = {}
    keep_cols: list[str] = []

    for m in mappings:
        raw = m["raw_column"]
        if m["status"] == "accepted":
            target = m.get("curator_field") or m.get("matched_field")
            if target and raw in raw_df.columns:
                rename_map[raw] = target
                keep_cols.append(raw)
        elif m["status"] == "pending" and m["matched_field"]:
            # Include pending but mapped columns with original matched field
            rename_map[raw] = m["matched_field"]
            keep_cols.append(raw)

    if not keep_cols:
        # Fallback: include all mapped columns
        for m in mappings:
            raw = m["raw_column"]
            if m["matched_field"] and raw in raw_df.columns:
                rename_map[raw] = m["matched_field"]
                keep_cols.append(raw)

    # Deduplicate keep_cols preserving order
    seen: set[str] = set()
    unique_keep: list[str] = []
    for c in keep_cols:
        if c not in seen:
            seen.add(c)
            unique_keep.append(c)

    out_df = raw_df[unique_keep].rename(columns=rename_map)
    return out_df.to_csv(index=False)


# ---------------------------------------------------------------------------
# cBioPortal Format
# ---------------------------------------------------------------------------

def export_cbioportal(study_id: str, raw_df: pd.DataFrame) -> str:
    """
    Produce a cBioPortal-format clinical data file.

    cBioPortal expects:
      Line 1: #Display names
      Line 2: #Descriptions
      Line 3: #Data types (STRING / NUMBER)
      Line 4: #Priority (1 for all)
      Line 5+: Header + data rows (tab-separated)
    """
    mappings = db.get_mappings(study_id)

    # Build column list from accepted / mapped
    cols: list[dict[str, Any]] = []
    for m in mappings:
        target = m.get("curator_field") or m.get("matched_field")
        if not target:
            continue
        if m["status"] not in ("accepted", "pending"):
            continue
        raw = m["raw_column"]
        if raw not in raw_df.columns:
            continue

        # Determine type
        dtype = "STRING"
        try:
            pd.to_numeric(raw_df[raw].dropna())
            dtype = "NUMBER"
        except (ValueError, TypeError):
            pass

        cols.append(
            {
                "raw": raw,
                "target": target.upper().replace(" ", "_"),
                "display": target.replace("_", " ").title(),
                "dtype": dtype,
            }
        )

    if not cols:
        return "# No mappings available for export\n"

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter="\t", lineterminator="\n")

    # Header lines
    writer.writerow(["#" + c["display"] for c in cols])
    writer.writerow(["#" + c["display"] for c in cols])
    writer.writerow(["#" + c["dtype"] for c in cols])
    writer.writerow(["#" + "1" for _ in cols])

    # Column IDs
    writer.writerow([c["target"] for c in cols])

    # Data rows
    for _, row in raw_df.iterrows():
        writer.writerow([row.get(c["raw"], "") for c in cols])

    return buf.getvalue()


# ---------------------------------------------------------------------------
# JSON Mapping Report
# ---------------------------------------------------------------------------

def export_mapping_report(study_id: str) -> str:
    """
    Produce a JSON audit report of all mapping decisions.
    """
    study = db.get_study(study_id)
    mappings = db.get_mappings(study_id)
    onto = db.get_ontology_mappings(study_id)
    audit = db.get_audit_log(study_id)

    report = {
        "study": study,
        "schema_mappings": mappings,
        "ontology_mappings": onto,
        "audit_log": audit,
        "summary": {
            "total_columns": len(mappings),
            "accepted": sum(1 for m in mappings if m["status"] == "accepted"),
            "rejected": sum(1 for m in mappings if m["status"] == "rejected"),
            "pending": sum(1 for m in mappings if m["status"] == "pending"),
        },
    }
    return json.dumps(report, indent=2, default=str)
