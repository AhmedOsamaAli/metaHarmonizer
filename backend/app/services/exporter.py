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
# Helpers
# ---------------------------------------------------------------------------

def _find_id_column(df: pd.DataFrame, candidates: list[str]) -> str:
    """
    Find the best existing column in `df` that matches one of the candidate
    names (case-insensitive).  If none found, return the first column that
    contains mostly unique non-null values (heuristic for an ID column).
    As a last resort, synthesize a column name — the exporter will fill it
    with row indices.
    """
    lower_cols = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower_cols:
            return lower_cols[cand.lower()]

    # Heuristic: find a column with high cardinality (likely an ID)
    for c in df.columns:
        non_null = df[c].dropna()
        if len(non_null) > 0 and non_null.nunique() / len(non_null) > 0.9:
            return c

    # Fallback: use first column
    return df.columns[0] if len(df.columns) > 0 else "_GENERATED_ID"


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
    Produce a cBioPortal-format clinical sample data file.

    Follows the official cBioPortal file format specification:
    https://docs.cbioportal.org/file-formats/#clinical-data

    cBioPortal clinical data files require:
      Row 1: #Display names
      Row 2: #Descriptions (longer description of each attribute)
      Row 3: #Data types (STRING, NUMBER, or BOOLEAN)
      Row 4: #Priority (numeric; higher = more prominent in UI)
      Row 5: Column attribute IDs (UPPER_CASE, no # prefix)
      Row 6+: Data rows (tab-separated)

    Required columns for sample-level data:
      - PATIENT_ID: unique patient identifier
      - SAMPLE_ID: unique sample identifier
    """
    mappings = db.get_mappings(study_id)

    # Build column list from accepted / mapped
    cols: list[dict[str, Any]] = []
    seen_targets: set[str] = set()

    for m in mappings:
        target = m.get("curator_field") or m.get("matched_field")
        if not target:
            continue
        if m["status"] not in ("accepted", "pending"):
            continue
        raw = m["raw_column"]
        if raw not in raw_df.columns:
            continue

        target_id = target.upper().replace(" ", "_")

        # Skip duplicate target columns
        if target_id in seen_targets:
            continue
        seen_targets.add(target_id)

        # Determine data type
        dtype = "STRING"
        try:
            pd.to_numeric(raw_df[raw].dropna())
            dtype = "NUMBER"
        except (ValueError, TypeError):
            # Check for boolean-like columns
            unique_vals = set(raw_df[raw].dropna().str.lower().unique())
            if unique_vals and unique_vals <= {"true", "false", "yes", "no", "0", "1"}:
                dtype = "BOOLEAN"

        # Priority: well-known cBioPortal attributes get higher priority
        priority = 1
        high_priority_attrs = {
            "PATIENT_ID", "SAMPLE_ID", "CANCER_TYPE", "CANCER_TYPE_DETAILED",
            "GENDER", "SEX", "AGE", "OS_STATUS", "OS_MONTHS", "TUMOR_SITE",
        }
        if target_id in high_priority_attrs:
            priority = 10

        cols.append(
            {
                "raw": raw,
                "target": target_id,
                "display": target.replace("_", " ").title(),
                "description": target.replace("_", " ").capitalize(),
                "dtype": dtype,
                "priority": priority,
            }
        )

    if not cols:
        return "# No mappings available for export\n"

    # ---------------------------------------------------------------
    # Ensure required columns PATIENT_ID and SAMPLE_ID are present.
    # cBioPortal sample clinical data REQUIRES both.
    # If the schema mapper matched subject_id or sample_id, they'll
    # already be in `cols`.  Otherwise, we synthesize them from
    # available data.
    # ---------------------------------------------------------------
    target_ids = {c["target"] for c in cols}

    if "PATIENT_ID" not in target_ids:
        # Try to find a suitable source column in the raw data
        patient_src = _find_id_column(raw_df, ["subject_id", "patient_id", "participant_id", "case_id"])
        cols.insert(0, {
            "raw": patient_src,
            "target": "PATIENT_ID",
            "display": "Patient Identifier",
            "description": "Unique patient identifier",
            "dtype": "STRING",
            "priority": 10,
        })
    else:
        # Move PATIENT_ID to front
        idx = next(i for i, c in enumerate(cols) if c["target"] == "PATIENT_ID")
        cols.insert(0, cols.pop(idx))

    if "SAMPLE_ID" not in target_ids:
        # Try to find a suitable source column in the raw data
        sample_src = _find_id_column(raw_df, ["sample_id", "run_id", "sampleid", "accession"])
        pos = 1  # right after PATIENT_ID
        cols.insert(pos, {
            "raw": sample_src,
            "target": "SAMPLE_ID",
            "display": "Sample Identifier",
            "description": "Unique sample identifier",
            "dtype": "STRING",
            "priority": 10,
        })
    else:
        # Move SAMPLE_ID to position 1 (right after PATIENT_ID)
        idx = next(i for i, c in enumerate(cols) if c["target"] == "SAMPLE_ID")
        if idx != 1:
            cols.insert(1, cols.pop(idx))

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter="\t", lineterminator="\n")

    # Row 1: Display names
    writer.writerow(["#" + c["display"] for c in cols])
    # Row 2: Descriptions (distinct from display names per spec)
    writer.writerow(["#" + c["description"] for c in cols])
    # Row 3: Data types
    writer.writerow(["#" + c["dtype"] for c in cols])
    # Row 4: Priority
    writer.writerow(["#" + str(c["priority"]) for c in cols])

    # Row 5: Column attribute IDs (no # prefix, UPPER_CASE)
    writer.writerow([c["target"] for c in cols])

    # Row 6+: Data rows
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
