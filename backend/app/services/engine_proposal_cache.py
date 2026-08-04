from __future__ import annotations

import json
from typing import Any

import pandas as pd

from app.core.storage import get_storage
from app.repositories import learned_decisions as learned_repo
from app.services.harmonizer import supports_ontology_mapping


def scopes(
    *,
    schema_version_id: int | None,
    ontology_snapshot_id: int | None,
    target_schema: str | None,
    engine_version: str | None,
) -> tuple[str, str]:
    schema_identity = str(schema_version_id or target_schema or "default")
    engine_identity = engine_version or "unknown"
    schema_scope = f"schema:v1:{schema_identity}:{engine_identity}"
    ontology_scope = (
        f"ontology:v1:{schema_identity}:{ontology_snapshot_id or 0}:{engine_identity}"
    )
    return schema_scope, ontology_scope


def read_columns(file_key: str, suffix: str) -> list[str]:
    sep = "\t" if suffix in (".tsv", ".txt") else ","
    with get_storage().local(file_key) as local_csv:
        return list(pd.read_csv(local_csv, sep=sep, nrows=0).columns)


def schema_keys(columns: list[str]) -> dict[str, str]:
    return {learned_repo.schema_key(column): column for column in columns}


def hydrate_schema(
    columns: list[str], cached: dict[str, dict]
) -> list[dict] | None:
    keys = schema_keys(columns)
    if len(keys) != len(columns):
        return None
    if set(cached) != set(keys):
        return None
    rows: list[dict] = []
    for key, column in keys.items():
        row = dict(cached[key])
        row["raw_column"] = column
        rows.append(row)
    return rows


def ontology_inputs(
    file_key: str,
    suffix: str,
    schema_rows: list[dict],
    ontology_columns: list[str] | None,
) -> dict[str, tuple[str, str]]:
    sep = "\t" if suffix in (".tsv", ".txt") else ","
    scope = {column.strip() for column in (ontology_columns or []) if column.strip()}
    with get_storage().local(file_key) as local_csv:
        raw_df = pd.read_csv(local_csv, sep=sep, low_memory=False)

    inputs: dict[str, tuple[str, str]] = {}
    for mapping in schema_rows:
        raw_column = mapping.get("raw_column")
        field = mapping.get("curator_field") or mapping.get("matched_field")
        if not raw_column or raw_column not in raw_df.columns:
            continue
        if scope and raw_column not in scope:
            continue
        if not supports_ontology_mapping(field):
            continue
        for value in raw_df[raw_column].dropna().unique():
            raw_value = str(value)
            if not raw_value.strip():
                continue
            key = learned_repo.ontology_key(str(field), raw_value)
            inputs[key] = (str(field), raw_value)
    return inputs


def hydrate_ontology(
    inputs: dict[str, tuple[str, str]], cached: dict[str, dict]
) -> list[dict] | None:
    if set(cached) != set(inputs):
        return None
    rows: list[dict] = []
    for key, (field, raw_value) in inputs.items():
        row = dict(cached[key])
        row["field_name"] = field
        row["raw_value"] = raw_value
        rows.append(row)
    return rows


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=lambda item: item.item()))


def schema_proposals(rows: list[dict]) -> dict[str, dict]:
    return {
        learned_repo.schema_key(row.get("raw_column") or ""): _jsonable(row)
        for row in rows
        if row.get("raw_column")
    }


def ontology_proposals(rows: list[dict]) -> dict[str, dict]:
    return {
        learned_repo.ontology_key(
            row.get("field_name") or "", row.get("raw_value") or ""
        ): _jsonable(row)
        for row in rows
        if row.get("field_name") and row.get("raw_value") is not None
    }
