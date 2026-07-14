"""Selectable target schemas for the schema mapper.

Discovers the SchemaRegistry artifacts installed under
``backend/data/schema/registry/<name>/`` — each carrying a
``<key>_target_attrs.csv`` (+ optional alias / allowed-values siblings) — so a
curator can choose which target schema an upload is mapped against (GDC,
cBioPortal, cMD, …).

Reads CSV/JSON only — it does **not** import ``metaharmonizer`` — so routers can
list the choices without paying the engine's torch import cost.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_REGISTRY_DIR = Path(__file__).resolve().parents[2] / "data" / "schema" / "registry"

# Friendly labels + a stable display order for the known schemas.
_LABELS: dict[str, str] = {
    "cbioportal": "cBioPortal",
    "gdc": "GDC — cancer (CPTAC)",
    "cmd": "curatedMetagenomicData",
    "omicsmlprepo_cbio": "OmicsMLRepo cBioPortal",
}
_ORDER = ["cbioportal", "gdc", "cmd", "omicsmlprepo_cbio"]

_SUFFIX = "_target_attrs.csv"


def _field_count(path: Path) -> int:
    try:
        with open(path, encoding="utf-8") as fh:
            return max(0, sum(1 for _ in fh) - 1)  # minus header
    except Exception:  # noqa: BLE001
        return 0


@lru_cache(maxsize=1)
def _discover() -> dict[str, dict]:
    found: dict[str, dict] = {}
    if not _REGISTRY_DIR.is_dir():
        return found
    for sub in sorted(_REGISTRY_DIR.iterdir()):
        if not sub.is_dir():
            continue
        target = next(iter(sorted(sub.glob(f"*{_SUFFIX}"))), None)
        if not target:
            continue
        key = target.name[: -len(_SUFFIX)]
        alias = next(iter(sorted(sub.glob("*_target_attrs_alias*.csv"))), None)
        values = next(iter(sorted(sub.glob("*_target_attrs_allowed_values.json"))), None)
        found[key] = {
            "key": key,
            "label": _LABELS.get(key, key),
            "fields": _field_count(target),
            "target_schema_path": str(target),
            "alias_dict_path": str(alias) if alias else None,
            "value_dict_path": str(values) if values else None,
        }
    return found


def available_schemas() -> list[dict]:
    """Public list (key, label, fields) for the picker — no filesystem paths."""
    found = _discover()
    ordered = [found[k] for k in _ORDER if k in found]
    ordered += [v for k, v in found.items() if k not in _ORDER]
    return [{"key": s["key"], "label": s["label"], "fields": s["fields"]} for s in ordered]


def resolve(key: str | None) -> dict | None:
    """Full record (incl. paths) for a schema key, or None."""
    if not key:
        return None
    return _discover().get(key)


def default_key() -> str:
    """Default schema when none is chosen: ``ENGINE_TARGET_SCHEMA`` if it names an
    installed schema, else cBioPortal, else the first available."""
    env = os.getenv("ENGINE_TARGET_SCHEMA")
    if env and env in _discover():
        return env
    if "cbioportal" in _discover():
        return "cbioportal"
    keys = list(_discover())
    return keys[0] if keys else "cbioportal"


def is_valid(key: str | None) -> bool:
    return bool(key) and key in _discover()
