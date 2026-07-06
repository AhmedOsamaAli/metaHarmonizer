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
import re
import zipfile
from typing import Any

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import audit as audit_repo
from app.repositories import mappings as mappings_repo
from app.repositories import ontology as ontology_repo
from app.repositories import studies as studies_repo


# cBioPortal auto-populates these; they must not appear in a clinical data file.
BANNED_ATTRS: set[str] = {"MUTATION_COUNT", "FRACTION_GENOME_ALTERED"}

# Checklist: columns to strip before import (verbatim from the Study-checklist;
# extensible). Matched against the normalized attribute id and raw column name.
BANNED_SOURCE_COLUMNS: set[str] = {
    "PART_A_CONSENT",
    "PART_C_CONSENT",
    "MSI_COMMENTS",
    "IMPACT_CVR_TMB",
    "IMPACT_TMB",
    "COLLABORATION_ID",
    "PATIENTCURRENTAGE",
    "RELIGION",
}

# Smart (curly) quotes the checklist forbids in field values.
_SMART_QUOTES = str.maketrans({
    "\u201c": '"', "\u201d": '"',  # “ ”
    "\u2018": "'", "\u2019": "'",  # ‘ ’
})


def _norm_attr(name: str) -> str:
    """Normalize a column/attribute name for blocklist comparison."""
    return re.sub(r"[^A-Za-z0-9]+", "_", str(name).strip()).strip("_").upper()


def _is_banned(target_id: str, raw_column: str) -> bool:
    """True if the column is checklist-banned (by target id or raw name)."""
    if target_id in BANNED_ATTRS:
        return True
    return (
        _norm_attr(target_id) in BANNED_SOURCE_COLUMNS
        or _norm_attr(raw_column) in BANNED_SOURCE_COLUMNS
    )


def _strip_smart_quotes(text: str) -> str:
    """Replace curly quotes with straight ones (checklist: no smart quotes)."""
    return text.translate(_SMART_QUOTES)

# Patient-level clinical attributes (cBioPortal convention). When a study is
# exported as a folder, these go to data_clinical_patient.txt and everything
# else (that isn't an ID) goes to data_clinical_sample.txt. Survival columns
# (``*_STATUS`` / ``*_MONTHS``) are always patient-level.
PATIENT_LEVEL_ATTRS: set[str] = {
    "SEX",
    "GENDER",
    "AGE",
    "AGE_AT_DIAGNOSIS",
    "RACE",
    "ETHNICITY",
    "ANCESTRY",
    "VITAL_STATUS",
    "OS_STATUS",
    "OS_MONTHS",
    "DFS_STATUS",
    "DFS_MONTHS",
    "PFS_STATUS",
    "PFS_MONTHS",
    "DSS_STATUS",
    "DSS_MONTHS",
}


def _is_patient_level(target_id: str) -> bool:
    """True if a cBioPortal attribute belongs in the patient clinical file."""
    if target_id in PATIENT_LEVEL_ATTRS:
        return True
    # Survival pairs use a free PREFIX (e.g. ``OS_STATUS`` / ``RFS_MONTHS``).
    return target_id.endswith("_STATUS") or target_id.endswith("_MONTHS")


# cBioPortal IDs allow only letters, numbers, points, underscores and hyphens.
_ID_INVALID = re.compile(r"[^A-Za-z0-9._-]")

# Survival *_STATUS values must be prefixed 0: (no event) or 1: (event).
_SURVIVAL_PREFIX: dict[str, str] = {
    "LIVING": "0:LIVING",
    "ALIVE": "0:LIVING",
    "DECEASED": "1:DECEASED",
    "DEAD": "1:DECEASED",
    "DISEASEFREE": "0:DiseaseFree",
    "DISEASE FREE": "0:DiseaseFree",
    "RECURRED": "1:Recurred/Progressed",
    "PROGRESSED": "1:Recurred/Progressed",
    "RECURRED/PROGRESSED": "1:Recurred/Progressed",
}


# Helpers


def _sanitize_id(value: Any) -> str:
    """Coerce a value into a cBioPortal-legal ID (letters, numbers, . _ -)."""
    text = "" if pd.isna(value) else str(value)
    return _ID_INVALID.sub("_", text)


def _normalize_survival(value: Any) -> str:
    """Prefix a survival-status value with 0:/1: if it isn't already."""
    text = "" if pd.isna(value) else str(value).strip()
    if not text or text[:2] in ("0:", "1:"):
        return text
    return _SURVIVAL_PREFIX.get(text.upper(), text)

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


# Harmonized CSV

async def export_harmonized_csv(
    db: AsyncSession, study_id: str, raw_df: pd.DataFrame
) -> str:
    """
    Produce a harmonized CSV: rename raw columns to their accepted/curated
    mappings, drop unmapped columns, rewrite accepted cell values to their
    confirmed ontology terms (U5), and return CSV text.
    """
    mappings = await mappings_repo.get_mappings(db, study_id)

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

    # Value-level rewrite (U5): for each output column, replace accepted raw
    # values with their confirmed ontology term so the table carries resolved
    # cell values — not just renamed columns. Unmatched values pass through.
    value_rewrites = await _build_value_rewrites(db, study_id)
    for col, lookup in value_rewrites.items():
        if col in out_df.columns:
            out_df[col] = out_df[col].map(
                lambda v, _m=lookup: _m.get(str(v), v) if pd.notna(v) else v
            )

    return out_df.to_csv(index=False)


async def _build_value_rewrites(
    db: AsyncSession, study_id: str
) -> dict[str, dict[str, str]]:
    """Map each harmonized field to its accepted ``raw_value -> term`` rewrites."""
    rewrites: dict[str, dict[str, str]] = {}
    for o in await ontology_repo.get_ontology_mappings(db, study_id):
        if o["status"] != "accepted":
            continue
        term = o.get("curator_term") or o.get("ontology_term")
        if not term:
            continue
        rewrites.setdefault(o["field_name"], {})[str(o["raw_value"])] = str(term)
    return rewrites


# cBioPortal Format

_HIGH_PRIORITY_ATTRS: set[str] = {
    "PATIENT_ID", "SAMPLE_ID", "CANCER_TYPE", "CANCER_TYPE_DETAILED",
    "GENDER", "SEX", "AGE", "OS_STATUS", "OS_MONTHS", "TUMOR_SITE",
}


def _infer_dtype(series: pd.Series) -> str:
    """Infer a cBioPortal data type (NUMBER / BOOLEAN / STRING) for a column."""
    non_null = series.dropna()
    try:
        pd.to_numeric(non_null)
        return "NUMBER"
    except (ValueError, TypeError):
        pass
    try:
        unique_vals = set(non_null.astype(str).str.lower().unique())
    except (AttributeError, TypeError):
        unique_vals = set()
    if unique_vals and unique_vals <= {"true", "false", "yes", "no", "0", "1"}:
        return "BOOLEAN"
    return "STRING"


def _clinical_column_specs(
    mappings: list[dict[str, Any]], raw_df: pd.DataFrame
) -> list[dict[str, Any]]:
    """Build cBioPortal column specs from accepted/pending mappings.

    Excludes PATIENT_ID / SAMPLE_ID (injected per-file by the caller) and
    banned auto-populated attributes; dedupes by target column.
    """
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
        if _is_banned(target_id, raw) or target_id in {"PATIENT_ID", "SAMPLE_ID"}:
            continue
        if target_id in seen_targets:
            continue
        seen_targets.add(target_id)
        cols.append(
            {
                "raw": raw,
                "target": target_id,
                "display": target.replace("_", " ").title(),
                "description": target.replace("_", " ").capitalize(),
                "dtype": _infer_dtype(raw_df[raw]),
                "priority": 10 if target_id in _HIGH_PRIORITY_ATTRS else 1,
            }
        )
    return cols


def _id_spec(
    target_id: str, raw_src: str, display: str, description: str
) -> dict[str, Any]:
    return {
        "raw": raw_src,
        "target": target_id,
        "display": display,
        "description": description,
        "dtype": "STRING",
        "priority": 10,
    }


def _id_raw_source(
    mappings: list[dict[str, Any]],
    raw_df: pd.DataFrame,
    target_id: str,
    fallback_candidates: list[str],
) -> str:
    """Find the raw column feeding an ID attribute: a matched mapping or a heuristic."""
    for m in mappings:
        target = m.get("curator_field") or m.get("matched_field")
        if not target:
            continue
        if target.upper().replace(" ", "_") == target_id and m.get("raw_column") in raw_df.columns:
            return m["raw_column"]
    return _find_id_column(raw_df, fallback_candidates)


def _write_clinical_tsv(
    cols: list[dict[str, Any]],
    raw_df: pd.DataFrame,
    value_rewrites: dict[str, dict[str, str]] | None = None,
) -> str:
    """Write a cBioPortal 5-row-header clinical TSV for the given column specs.

    ``value_rewrites`` maps a target attribute id (e.g. ``SEX``) to a
    ``raw_value -> confirmed term`` lookup so the exported cells carry the
    curator-resolved values (U5), not the raw ones.
    """
    rewrites = value_rewrites or {}
    targets = {c["target"] for c in cols}
    survival_status_with_months = {
        c["target"]
        for c in cols
        if c["target"].endswith("_STATUS") and f"{c['target'][:-7]}_MONTHS" in targets
    }
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter="\t", lineterminator="\n")

    def _header_row(values: list[str]) -> None:
        # Per spec, only the FIRST field of each metadata row carries the '#'.
        row = list(values)
        if row:
            row[0] = "#" + row[0]
        writer.writerow(row)

    _header_row([c["display"] for c in cols])
    _header_row([c["description"] for c in cols])
    _header_row([c["dtype"] for c in cols])
    _header_row([str(c["priority"]) for c in cols])
    writer.writerow([c["target"] for c in cols])  # attribute IDs (no '#')

    for _, row in raw_df.iterrows():
        out_row: list[str] = []
        for c in cols:
            raw_val = row.get(c["raw"], "")
            target_id = c["target"]
            if target_id in ("PATIENT_ID", "SAMPLE_ID"):
                out_row.append(_sanitize_id(raw_val))
            elif target_id in survival_status_with_months:
                out_row.append(_normalize_survival(raw_val))
            else:
                # Apply the curator-confirmed value rewrite (U5) so the cell
                # carries the resolved term; fall back to the raw value. pandas
                # NaN is not None, so guard with isna to avoid the literal "nan".
                if pd.isna(raw_val):
                    out_row.append("")
                else:
                    lookup = rewrites.get(target_id)
                    text = str(raw_val)
                    text = lookup.get(text, text) if lookup else text
                    out_row.append(_strip_smart_quotes(text))
        writer.writerow(out_row)

    return buf.getvalue()


def _rewrites_by_target(
    field_rewrites: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    """Re-key field-name rewrites to cBioPortal target ids (UPPER_CASE)."""
    return {
        field.upper().replace(" ", "_"): lookup
        for field, lookup in field_rewrites.items()
    }


async def export_cbioportal(
    db: AsyncSession, study_id: str, raw_df: pd.DataFrame
) -> str:
    """
    Produce a single cBioPortal-format clinical data file (all attributes in
    one sample-level file), per the official spec:
    https://docs.cbioportal.org/file-formats/#clinical-data

    Header rows: display names, descriptions, data types, priority, then the
    UPPER_CASE attribute IDs. PATIENT_ID and SAMPLE_ID are always present.
    Curator-confirmed value rewrites (U5) are applied to the cells.
    """
    mappings = await mappings_repo.get_mappings(db, study_id)
    specs = _clinical_column_specs(mappings, raw_df)

    patient_src = _id_raw_source(
        mappings, raw_df, "PATIENT_ID",
        ["subject_id", "patient_id", "participant_id", "case_id"],
    )
    sample_src = _id_raw_source(
        mappings, raw_df, "SAMPLE_ID",
        ["sample_id", "run_id", "sampleid", "accession"],
    )

    if not specs and raw_df.columns.empty:
        return "# No mappings available for export\n"

    cols = [
        _id_spec("PATIENT_ID", patient_src, "Patient Identifier", "Unique patient identifier"),
        _id_spec("SAMPLE_ID", sample_src, "Sample Identifier", "Unique sample identifier"),
        *specs,
    ]
    rewrites = _rewrites_by_target(await _build_value_rewrites(db, study_id))
    return _write_clinical_tsv(cols, raw_df, rewrites)


# cBioPortal study folder (validateData.py-ready)

def _meta_study(cancer_study_identifier: str, name: str, description: str) -> str:
    # No ``add_global_case_list`` — the checklist says not to use it; we ship an
    # explicit case_lists/cases_all.txt instead (and the two would collide).
    return (
        f"type_of_cancer: mixed\n"
        f"cancer_study_identifier: {cancer_study_identifier}\n"
        f"name: {name}\n"
        f"description: {description}\n"
    )


def _meta_clinical(cancer_study_identifier: str, datatype: str, data_filename: str) -> str:
    return (
        f"cancer_study_identifier: {cancer_study_identifier}\n"
        f"genetic_alteration_type: CLINICAL\n"
        f"datatype: {datatype}\n"
        f"data_filename: {data_filename}\n"
    )


def _case_list_all(cancer_study_identifier: str, sample_ids: list[str]) -> str:
    """The ``cases_all.txt`` case list (every sample in the study).

    cBioPortal expects a tab-separated list of sample IDs under
    ``case_lists/cases_all.txt`` with the ``<study>_all`` stable id.
    """
    ids = "\t".join(sample_ids)
    return (
        f"cancer_study_identifier: {cancer_study_identifier}\n"
        f"stable_id: {cancer_study_identifier}_all\n"
        f"case_list_category: all_cases_in_study\n"
        f"case_list_name: All samples\n"
        f"case_list_description: All samples ({len(sample_ids)} samples)\n"
        f"case_list_ids: {ids}\n"
    )


# Permissive OSS license shipped in the study folder (checklist: "make sure the
# LICENSE is added to the study folder"). The harmonized clinical data is the
# curators' to license; we ship a CC0 public-domain dedication as a safe default
# for public datahub studies. Curators can replace it.
_LICENSE_TEXT = (
    "CC0 1.0 Universal (CC0 1.0) Public Domain Dedication\n"
    "\n"
    "This clinical study folder was harmonized with MetaHarmonizer. The data\n"
    "curators are the source of, and hold any rights to, the underlying data.\n"
    "To the extent possible under law, the curators have waived all copyright\n"
    "and related or neighboring rights to this dataset. Replace this file with\n"
    "the license that applies to your data before distribution.\n"
    "\n"
    "See https://creativecommons.org/publicdomain/zero/1.0/ for the full text.\n"
)


def _sample_ids_for_case_list(raw_df: pd.DataFrame, sample_src: str) -> list[str]:
    """Sanitized, de-duplicated sample IDs in first-seen order."""
    if sample_src not in raw_df.columns:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for v in raw_df[sample_src]:
        sid = _sanitize_id(v)
        if sid and sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out


async def export_cbioportal_study(
    db: AsyncSession,
    study_id: str,
    raw_df: pd.DataFrame,
    cancer_study_identifier: str | None = None,
) -> bytes:
    """
    Produce a cBioPortal study folder as a zip, ready for ``validateData.py``:

        meta_study.txt
        meta_clinical_patient.txt
        data_clinical_patient.txt
        meta_clinical_sample.txt
        data_clinical_sample.txt
        case_lists/cases_all.txt
        LICENSE

    The clinical attributes are split per the curation checklist ("the clinical
    file should be split to patient and sample level attribute files"):
    patient-level attributes (sex, survival, age, ancestry, ...) go to the
    patient file with one row per unique patient; everything else goes to the
    sample file with one row per sample. PATIENT_ID appears in both so samples
    link to patients.
    """
    study = await studies_repo.get_study(db, study_id) or {}
    identifier = cancer_study_identifier or _sanitize_id(
        study.get("name") or study_id
    ).lower()
    name = study.get("name") or study_id
    description = study.get("description") or f"Harmonized clinical data for {name}."

    mappings = await mappings_repo.get_mappings(db, study_id)
    specs = _clinical_column_specs(mappings, raw_df)

    patient_src = _id_raw_source(
        mappings, raw_df, "PATIENT_ID",
        ["subject_id", "patient_id", "participant_id", "case_id"],
    )
    sample_src = _id_raw_source(
        mappings, raw_df, "SAMPLE_ID",
        ["sample_id", "run_id", "sampleid", "accession"],
    )

    patient_id_spec = _id_spec(
        "PATIENT_ID", patient_src, "Patient Identifier", "Unique patient identifier"
    )
    sample_id_spec = _id_spec(
        "SAMPLE_ID", sample_src, "Sample Identifier", "Unique sample identifier"
    )

    patient_attr_specs = [s for s in specs if _is_patient_level(s["target"])]
    sample_attr_specs = [s for s in specs if not _is_patient_level(s["target"])]

    # Patient file: one row per unique patient (cBioPortal requires unique
    # PATIENT_ID rows). Sample file: one row per sample, PATIENT_ID links back.
    patient_cols = [patient_id_spec, *patient_attr_specs]
    sample_cols = [patient_id_spec, sample_id_spec, *sample_attr_specs]

    patient_df = raw_df.drop_duplicates(subset=[patient_src]) if patient_src in raw_df.columns else raw_df

    rewrites = _rewrites_by_target(await _build_value_rewrites(db, study_id))
    data_clinical_patient = _write_clinical_tsv(patient_cols, patient_df, rewrites)
    data_clinical_sample = _write_clinical_tsv(sample_cols, raw_df, rewrites)
    sample_ids = _sample_ids_for_case_list(raw_df, sample_src)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("meta_study.txt", _meta_study(identifier, name, description))
        zf.writestr(
            "meta_clinical_patient.txt",
            _meta_clinical(identifier, "PATIENT_ATTRIBUTES", "data_clinical_patient.txt"),
        )
        zf.writestr("data_clinical_patient.txt", data_clinical_patient)
        zf.writestr(
            "meta_clinical_sample.txt",
            _meta_clinical(identifier, "SAMPLE_ATTRIBUTES", "data_clinical_sample.txt"),
        )
        zf.writestr("data_clinical_sample.txt", data_clinical_sample)
        if sample_ids:
            zf.writestr("case_lists/cases_all.txt", _case_list_all(identifier, sample_ids))
        zf.writestr("LICENSE", _LICENSE_TEXT)
    return buf.getvalue()


# Labeled dataset export (G9 — curator-confirmed mappings for retraining)

LABELED_FIELDNAMES = [
    "record_type",
    "raw_column",
    "raw_sample_values",
    "accepted_target",
    "ontology_id",
    "confidence",
    "stage",
    "method",
    "schema_version",
    "ontology_version",
]


def _distinct_sample_values(raw_df: pd.DataFrame, column: str, limit: int = 5) -> str:
    """Up to ``limit`` distinct non-null values from a raw column, ';'-joined."""
    if column not in raw_df.columns:
        return ""
    seen: list[str] = []
    for v in raw_df[column]:
        if pd.isna(v):
            continue
        s = str(v).strip()
        if s and s not in seen:
            seen.append(s)
        if len(seen) >= limit:
            break
    return ";".join(seen)


async def _labeled_rows(
    db: AsyncSession, study_id: str, raw_df: pd.DataFrame
) -> list[dict[str, Any]]:
    """Curator-confirmed mappings as labeled training rows (G9).

    Two record types in one dataset:
    - ``schema_mapping``: an accepted raw column -> target field, with a few
      distinct sample values as the input signal.
    - ``ontology_mapping``: an accepted value -> ontology term/id.

    Only **accepted** (human-confirmed) decisions are emitted — this is a
    labeled dataset, not the raw engine output.
    """
    study = await studies_repo.get_study(db, study_id) or {}
    schema_version = study.get("schema_version_id")
    schema_version = "" if schema_version is None else str(schema_version)

    rows: list[dict[str, Any]] = []

    for m in await mappings_repo.get_mappings(db, study_id):
        if m["status"] != "accepted":
            continue
        target = m.get("curator_field") or m.get("matched_field")
        if not target:
            continue
        rows.append(
            {
                "record_type": "schema_mapping",
                "raw_column": m["raw_column"],
                "raw_sample_values": _distinct_sample_values(raw_df, m["raw_column"]),
                "accepted_target": target,
                "ontology_id": "",
                "confidence": m.get("confidence_score") or "",
                "stage": m.get("stage") or "",
                "method": m.get("method") or "",
                "schema_version": schema_version,
                "ontology_version": "",
            }
        )

    for o in await ontology_repo.get_ontology_mappings(db, study_id):
        if o["status"] != "accepted":
            continue
        term = o.get("curator_term") or o.get("ontology_term")
        if not term:
            continue
        rows.append(
            {
                "record_type": "ontology_mapping",
                "raw_column": o["field_name"],
                "raw_sample_values": str(o["raw_value"]),
                "accepted_target": term,
                "ontology_id": o.get("ontology_id") or "",
                "confidence": o.get("confidence_score") or "",
                "stage": "",
                "method": "",
                "schema_version": schema_version,
                "ontology_version": "",
            }
        )

    return rows


async def export_labeled_dataset(
    db: AsyncSession, study_id: str, raw_df: pd.DataFrame, fmt: str = "csv"
) -> str:
    """Curator-confirmed mappings as a labeled dataset (G9), CSV or JSONL.

    Row shape: (record_type, raw_column, raw_sample_values, accepted_target,
    ontology_id, confidence, stage, method, schema_version, ontology_version).
    """
    rows = await _labeled_rows(db, study_id, raw_df)

    if fmt == "jsonl":
        return "\n".join(json.dumps(r, default=str) for r in rows) + ("\n" if rows else "")

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=LABELED_FIELDNAMES, lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue()


# LinkML export gate (G9 — controlled-vocabulary check before export)


def _parse_clinical_columns(tsv_text: str) -> dict[str, list[str]]:
    """Parse a cBioPortal clinical TSV back into ``{attr_id: [values]}``.

    The 5th line (index 4) is the UPPER_CASE attribute id row; data follows.
    """
    lines = tsv_text.split("\n")
    if len(lines) <= 5:
        return {}
    header = lines[4].split("\t")
    columns: dict[str, list[str]] = {h: [] for h in header}
    for line in lines[5:]:
        if not line:
            continue
        cells = line.split("\t")
        for i, h in enumerate(header):
            columns[h].append(cells[i] if i < len(cells) else "")
    return columns


async def linkml_check(
    db: AsyncSession, study_id: str, raw_df: pd.DataFrame
) -> dict[str, Any]:
    """Run the LinkML controlled-vocabulary gate on the harmonized output.

    Validates the exact cBioPortal sample-file values (after curator value
    rewrites + survival prefixing) against the checklist vocabularies. Returns
    ``{"ok": bool, "violations": [...]}``.
    """
    from app.services import linkml_gate

    tsv = await export_cbioportal(db, study_id, raw_df)
    columns = _parse_clinical_columns(tsv)
    violations = linkml_gate.validate_clinical_columns(columns)
    return {"ok": not violations, "violations": violations}


# JSON Mapping Report

async def export_mapping_report(db: AsyncSession, study_id: str) -> str:
    """
    Produce a JSON audit report of all mapping decisions.
    """
    study = await studies_repo.get_study(db, study_id)
    mappings = await mappings_repo.get_mappings(db, study_id)
    onto = await ontology_repo.get_ontology_mappings(db, study_id)
    audit = await audit_repo.get_audit_log(db, study_id)

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
