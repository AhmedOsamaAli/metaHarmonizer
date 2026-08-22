"""Admin management of the schema-mapper dictionaries (aliases + fields).

Lives in ``engine_adapter`` because reading the engine's *bundled* preset
dictionaries requires importing ``metaharmonizer`` — which the engine-boundary
rule permits only here. Routers call these helpers instead of importing the
engine themselves.

Two alias layers, mirroring ``metaharmonizer_impl``:
  • built-in — the preset's bundled alias dictionary (read-only, ~1k rows).
  • admin    — ``data/schema/aliases/current.alias.csv`` (uploaded / hand-added).
The merged view (built-in + admin) is what the schema mapper actually uses.
"""

from __future__ import annotations

import importlib.util
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ALIAS_DIR = Path(__file__).resolve().parents[2] / "data" / "schema" / "aliases"
_ADMIN_ALIAS = _ALIAS_DIR / "current.alias.csv"
_MERGED_ALIAS = _ALIAS_DIR / "merged.alias.csv"


def _schema_name() -> str:
    return os.getenv("ENGINE_TARGET_SCHEMA", "cbio")


@lru_cache(maxsize=1)
def _bundled_schema_dir() -> Path | None:
    """Locate the engine's bundled preset-schema directory *without importing*
    the ``metaharmonizer`` package.

    ``importlib.util.find_spec`` resolves the package location without executing
    its ``__init__`` — critical, because importing the engine drags in
    ``sentence_transformers``/torch (~15s), which would otherwise freeze the
    event loop on the first admin-page load (even on the mock backend).
    """
    try:
        spec = importlib.util.find_spec("metaharmonizer")
        if not spec or not spec.origin:
            return None
        d = Path(spec.origin).parent / "_bundled_data" / "schema"
        return d if d.is_dir() else None
    except Exception:  # noqa: BLE001
        return None


def _preset_target_schema_path() -> Path | None:
    d = _bundled_schema_dir()
    if not d:
        return None
    p = d / f"{_schema_name()}_target_attrs.csv"
    return p if p.exists() else None


def _preset_alias_path() -> Path | None:
    d = _bundled_schema_dir()
    if not d:
        return None
    matches = sorted(d.glob(f"{_schema_name()}_target_attrs_alias*.csv"))
    return matches[0] if matches else None


def schema_field_names() -> list[str]:
    """Valid target field names for the active schema preset (for validation).

    Reads the bundled schema CSV directly — no engine import.
    """
    try:
        import pandas as pd

        path = _preset_target_schema_path()
        if not path:
            return []
        df = pd.read_csv(path)
        return sorted(df["field_name"].dropna().astype(str).unique().tolist())
    except Exception:  # noqa: BLE001 — never break the admin page over this
        logger.warning("schema_field_names: could not read preset schema", exc_info=True)
        return []


def _read_csv(path):
    import pandas as pd

    if path and Path(path).exists():
        try:
            return pd.read_csv(path)
        except Exception:  # noqa: BLE001
            return pd.DataFrame(columns=["source", "field_name"])
    return pd.DataFrame(columns=["source", "field_name"])


def alias_entries(query: str | None = None, limit: int = 500) -> dict[str, Any]:
    """Merged built-in + admin aliases, optionally filtered by substring.

    Each entry carries ``builtin`` — admin-added rows (``builtin=False``) are the
    only ones that can be removed; built-ins are read-only.
    """
    builtin = _read_csv(_preset_alias_path())
    admin = _read_csv(_ADMIN_ALIAS)

    def _pairs(df):
        out = set()
        for _, r in df.iterrows():
            src = str(r.get("source", "")).strip()
            fld = str(r.get("field_name", "")).strip()
            if src and fld:
                out.add((src.lower(), fld))
        return out

    admin_pairs = _pairs(admin)

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for _, r in list(admin.iterrows()) + list(builtin.iterrows()):
        src = str(r.get("source", "")).strip()
        fld = str(r.get("field_name", "")).strip()
        if not src or not fld:
            continue
        key = (src.lower(), fld)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"source": src, "field_name": fld, "builtin": key not in admin_pairs})

    if query:
        q = query.strip().lower()
        rows = [r for r in rows if q in r["source"].lower() or q in r["field_name"].lower()]

    rows.sort(key=lambda r: (r["field_name"], r["source"].lower()))
    total = len(rows)
    return {"total": total, "returned": min(total, limit), "entries": rows[:limit]}


class AliasExists(Exception):
    """Raised when adding an alias that already exists (built-in or custom)."""


def _pair_exists(src: str, fld: str) -> str | None:
    """Return 'built-in' / 'custom' if the (alias, field) pair already exists,
    else ``None``. Checks both layers so duplicates are reported, not silently
    swallowed."""

    src_l, fld_s = src.strip().lower(), fld.strip()
    for df, label in ((_read_csv(_ADMIN_ALIAS), "custom"),
                      (_read_csv(_preset_alias_path()), "built-in")):
        if not len(df):
            continue
        hit = (
            df["source"].astype(str).str.strip().str.lower() == src_l
        ) & (df["field_name"].astype(str).str.strip() == fld_s)
        if hit.any():
            return label
    return None


def add_alias(source: str, field_name: str) -> None:
    """Append one admin alias. Raises :class:`AliasExists` if the (alias, field)
    pair is already present (built-in or custom), so callers can report it."""
    import pandas as pd

    src, fld = (source or "").strip(), (field_name or "").strip()
    if not src or not fld:
        raise ValueError("Both source and field_name are required.")

    where = _pair_exists(src, fld)
    if where:
        raise AliasExists(f"'{src}' → '{fld}' already exists ({where}).")

    df = _read_csv(_ADMIN_ALIAS)
    df = pd.concat(
        [df, pd.DataFrame([{"source": src, "field_name": fld}])], ignore_index=True
    )
    _ALIAS_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(_ADMIN_ALIAS, index=False)
    _invalidate()


def export_csv(scope: str = "merged") -> str:
    """Return the alias dictionary as CSV text (``source,field_name``).

    ``scope='merged'`` (default) exports built-in + admin; ``scope='custom'``
    exports only the admin-added aliases.
    """
    import io

    import pandas as pd

    if scope == "custom":
        df = _read_csv(_ADMIN_ALIAS)[["source", "field_name"]] if _ADMIN_ALIAS.exists() \
            else pd.DataFrame(columns=["source", "field_name"])
    else:
        rows = alias_entries(limit=10**9)["entries"]
        df = pd.DataFrame(
            [{"source": r["source"], "field_name": r["field_name"]} for r in rows]
        )
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def remove_alias(source: str, field_name: str) -> bool:
    """Remove one admin alias. Built-ins cannot be removed. Returns success."""
    if not _ADMIN_ALIAS.exists():
        return False
    df = _read_csv(_ADMIN_ALIAS)
    if not len(df):
        return False
    src, fld = (source or "").strip().lower(), (field_name or "").strip()
    mask = (
        df["source"].astype(str).str.strip().str.lower() == src
    ) & (df["field_name"].astype(str).str.strip() == fld)
    if not mask.any():
        return False
    df[~mask].to_csv(_ADMIN_ALIAS, index=False)
    _invalidate()
    return True


def _invalidate() -> None:
    """Drop the merged cache + rebuild the engine so the next harmonize picks up
    the change (fixes the per-process engine-cache staleness)."""
    try:
        if _MERGED_ALIAS.exists():
            _MERGED_ALIAS.unlink()
    except OSError:
        pass
    try:
        from . import reset_engine_cache

        reset_engine_cache()
    except Exception:  # noqa: BLE001
        pass
