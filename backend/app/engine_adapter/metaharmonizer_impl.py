"""MetaHarmonizerAdapter — wraps the upstream ``metaharmonizer`` package.

The ONLY file allowed to ``import metaharmonizer`` (enforced by
``scripts/check_engine_boundary.py``). Selected via ``ENGINE_IMPL=metaharmonizer``.
"""

from __future__ import annotations

import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from .types import EngineHealth


@lru_cache(maxsize=1)
def _auto_accept_threshold() -> float:
    """Confidence at/above which a mapping is auto-accepted (env-tunable per the
    spec's auto-accept / flag-for-review bands; ``AUTO_ACCEPT_THRESHOLD``)."""
    try:
        from app.core.settings import settings

        return float(settings.auto_accept_threshold)
    except Exception:  # noqa: BLE001 — never fail mapping over a config read
        return 0.9


_INSTALL_HINT = (
    "The 'metaharmonizer' package is not installed. Add\n"
    "  metaharmonizer @ git+https://github.com/shbrief/MetaHarmonizer@<sha>\n"
    "to backend/requirements.txt, then `pip install -r backend/requirements.txt`."
)

# Upstream reads schema files under ``$METAHARMONIZER_DATA_DIR/schema/``; fall
# back to the dashboard-owned copy so a fresh checkout works without config.
def _ensure_upstream_data_dir() -> None:
    if os.environ.get("METAHARMONIZER_DATA_DIR"):
        return
    here = Path(__file__).resolve()
    backend_data = here.parents[2] / "data"  # backend/data
    if (backend_data / "schema" / "ncit_descendants.json").exists():
        os.environ["METAHARMONIZER_DATA_DIR"] = str(backend_data)


def _require_pkg():
    try:
        _ensure_upstream_data_dir()
        import metaharmonizer  # noqa: F401  ← the one allowed import
        return metaharmonizer
    except ImportError as exc:  # pragma: no cover — environment-dependent
        raise RuntimeError(_INSTALL_HINT) from exc


class MetaHarmonizerAdapter:
    """Wraps the upstream pip-installed engine."""

    name = "metaharmonizer"

    def __init__(self, *, mode: str | None = None, top_k: int = 5):
        if mode is None:
            mode = "auto" if os.getenv("GEMINI_API_KEY") else "manual"
        self._mode = mode
        self._top_k = top_k
        # Pin "cbio" (33-field cBioPortal preset); the engine's own default is
        # "gdc" (736 fields). Override via ENGINE_TARGET_SCHEMA.
        self._schema = os.getenv("ENGINE_TARGET_SCHEMA", "cbio")

    # ------------------------------------------------------------------
    def _alias_dict_path(self) -> str | None:
        """Column-name alias dictionary path for the schema mapper.

        With no admin upload, returns ``None`` so the engine uses the preset's
        bundled alias dictionary. When an admin has uploaded aliases (written by
        ``POST /admin/schema-aliases`` in long ``source,field_name`` form), the
        upload is **merged** with the preset's built-in aliases — augmenting,
        not replacing them — and the merged file's path is returned. Uploaded
        rows win on any conflicting alias.
        """
        from pathlib import Path

        base = Path(__file__).resolve().parents[2] / "data" / "schema" / "aliases"
        admin = base / "current.alias.csv"
        if not admin.exists():
            return None

        merged = base / "merged.alias.csv"
        try:
            if not merged.exists() or merged.stat().st_mtime < admin.stat().st_mtime:
                self._build_merged_alias(admin, merged)
            return str(merged)
        except Exception:  # noqa: BLE001 — never break harmonize over aliases
            return str(admin)  # fall back to admin-only

    def _build_merged_alias(self, admin_path, merged_path) -> None:
        """Concatenate the preset's bundled aliases with the admin upload,
        de-duplicating by (normalized) alias so an upload augments the built-ins."""
        from pathlib import Path

        import pandas as pd

        _require_pkg()
        frames = []
        try:
            from metaharmonizer.models.schema_mapper import config as cfg

            preset = cfg.resolve_schema_preset(self._schema)
            preset_path = preset.get("alias_dict_path") if preset else None
            if preset_path and Path(preset_path).exists():
                frames.append(pd.read_csv(preset_path))
        except Exception:  # noqa: BLE001 — preset unavailable → admin-only merge
            pass

        admin_df = pd.read_csv(admin_path)  # columns: source, field_name
        if "is_numeric_field" not in admin_df.columns:
            admin_df["is_numeric_field"] = ""
        frames.append(admin_df)

        out = pd.concat(frames, ignore_index=True)
        # De-dup on the (alias, field) pair — never on alias alone: the engine
        # supports one alias mapping to several fields, so collapsing by alias
        # would silently drop built-in coverage. keep="last" lets an uploaded
        # row win an exact-pair clash.
        out["_k"] = out["source"].astype(str).str.strip().str.lower()
        out = (
            out.drop_duplicates(subset=["_k", "field_name"], keep="last")
            .drop(columns=["_k"])
        )
        merged_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(merged_path, index=False)

    @lru_cache(maxsize=8)
    def _engine_for(self, csv_path: str, schema_key: str):
        pkg = _require_pkg()
        from . import _perf, _schema_registry

        _perf.install_patches()
        SchemaMapEngine = pkg.SchemaMapEngine  # type: ignore[attr-defined]
        sch = _schema_registry.resolve(schema_key)
        if sch and sch.get("target_schema_path"):
            # A SchemaRegistry-installed target schema (GDC / cBioPortal / cMD /
            # …): pass explicit paths so the engine maps into it, along with its
            # matched alias / allowed-values dicts when present.
            kwargs: dict[str, Any] = {
                "target_schema_path": sch["target_schema_path"],
                "mode": self._mode,
                "top_k": self._top_k,
            }
            if sch.get("alias_dict_path"):
                kwargs["alias_dict_path"] = sch["alias_dict_path"]
            if sch.get("value_dict_path"):
                kwargs["value_dict_path"] = sch["value_dict_path"]
            return SchemaMapEngine(csv_path, **kwargs)
        # Fallback: treat the key as a bundled preset name (cbio / gdc).
        return SchemaMapEngine(
            csv_path,
            schema_key,
            mode=self._mode,
            top_k=self._top_k,
            alias_dict_path=self._alias_dict_path(),
        )

    # ------------------------------------------------------------------
    # EngineProtocol methods
    # ------------------------------------------------------------------
    def harmonize_schema(
        self,
        raw_df: pd.DataFrame,
        curated_df: pd.DataFrame,
        *,
        csv_path: str | None = None,
        target_schema: str | None = None,
    ) -> list[dict[str, Any]]:
        if not csv_path:
            raise ValueError("metaharmonizer adapter requires csv_path")
        from . import _schema_registry

        # Resolve the curator's chosen target schema: an installed SchemaRegistry
        # schema if valid, else the installed default, else the bundled preset.
        if _schema_registry.is_valid(target_schema):
            schema_key = target_schema
        elif _schema_registry.available_schemas():
            schema_key = _schema_registry.default_key()
        else:
            schema_key = self._schema
        engine = self._engine_for(csv_path, schema_key)
        raw = engine.run_schema_mapping()
        # Persist new NCI EVS lookups so later studies reuse them.
        from . import _perf

        _perf.save_nci_cache()
        return [self._to_dashboard_row(r) for r in raw.to_dict(orient="records")]

    def map_values(
        self,
        raw_df: pd.DataFrame,
        schema_mappings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        # Value-to-ontology mapping (F-11). Route the engine's first-class
        # categories (NCIt-disease, UBERON-bodysite, NCIt-treatment) through
        # OntoMapEngine when ONTOLOGY_ENGINE=1; otherwise (and on any failure or
        # missing corpus) fall back to the curated dictionary. EFO/HANCESTRO
        # need engine-team support and are intentionally excluded.
        from app.services.harmonizer import run_ontology_mapping

        from . import _ontology

        if not _ontology.engine_enabled():
            return run_ontology_mapping(raw_df, schema_mappings)

        try:
            pkg = _require_pkg()
            engine_rows, handled = _ontology.map_values_via_engine(
                pkg, raw_df, schema_mappings
            )
        except Exception:  # noqa: BLE001 — never let the engine path break mapping
            return run_ontology_mapping(raw_df, schema_mappings)

        # Dictionary fallback for the fields the engine didn't cover.
        remaining = [
            m
            for m in schema_mappings
            if (m.get("curator_field") or m.get("matched_field") or "").strip().lower()
            not in handled
        ]
        fallback_rows = run_ontology_mapping(raw_df, remaining) if remaining else []
        return engine_rows + fallback_rows

    def llm_match(self, csv_path: str, raw_column: str) -> list[dict[str, Any]]:
        if not os.getenv("GEMINI_API_KEY"):
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to the backend .env to use "
                "on-demand LLM matching."
            )
        pkg = _require_pkg()
        from . import _schema_registry

        # engine >=0.4.0: LLMMatcher moved to the stage-4 matchers module.
        try:
            LLMMatcher = pkg.LLMMatcher  # type: ignore[attr-defined]
        except AttributeError:
            from metaharmonizer.models.schema_mapper.matchers.stage4_matchers import (
                LLMMatcher,
            )
        schema_key = getattr(self, "_schema", None) or _schema_registry.default_key()
        engine = self._engine_for(csv_path, schema_key)
        matcher = LLMMatcher(engine)
        return [
            {"field": f, "confidence": round(float(s), 4), "reasoning": src}
            for (f, s, src) in matcher.match(raw_column)
        ]

    def pre_warm(self) -> None:
        # Pay the import + model-load cost at startup, not on the first user
        # request, and install the shared-model / persistent-NCI-cache patches
        # so every study after the first is fast.
        _require_pkg()
        from . import _perf

        _perf.install_patches()
        _perf.warm_model()
        # Warm the NCI EVS cache so the first upload skips ~90s of cold API calls.
        self._warm_nci_cache()

    def _warm_nci_cache(self) -> None:
        """Populate + persist the NCI cache by harmonizing a sample CSV.

        Best-effort and never raises. Controlled by ``ENGINE_WARM_SAMPLE``:
        a CSV path to use, or ``off``/``0``/``false``/``none`` to disable. When
        unset, falls back to the bundled ``metadata_samples/new_meta.csv``.
        """
        flag = os.getenv("ENGINE_WARM_SAMPLE")
        if flag and flag.strip().lower() in {"off", "0", "false", "none"}:
            return
        sample = Path(flag) if flag else self._default_warm_sample()
        if sample is None or not sample.exists():
            return
        try:
            df = pd.read_csv(sample, dtype=str)
            self.harmonize_schema(df, None, csv_path=str(sample))
        except Exception:  # pragma: no cover — warming must never break startup
            pass

    @staticmethod
    def _default_warm_sample() -> Path | None:
        here = Path(__file__).resolve()
        candidate = here.parents[3] / "metadata_samples" / "new_meta.csv"
        return candidate if candidate.exists() else None

    def health(self) -> EngineHealth:
        try:
            pkg = _require_pkg()
            version = getattr(pkg, "__version__", "unknown")
            return EngineHealth(
                ok=True,
                name=self.name,
                version=str(version),
                loaded_models=["all-MiniLM-L6-v2"],
            )
        except RuntimeError as exc:
            return EngineHealth(
                ok=False,
                name=self.name,
                version="not-installed",
                warnings=[str(exc)],
            )

    # ------------------------------------------------------------------
    # Translation — the ONE place that knows upstream column names.
    # ------------------------------------------------------------------
    @staticmethod
    def _is_missing(value: Any) -> bool:
        """True for None, empty string, or NaN float (NaN never equals itself)."""
        if value is None or value == "":
            return True
        if isinstance(value, float) and math.isnan(value):
            return True
        return False

    @staticmethod
    def _to_score(value: Any) -> float:
        """Coerce a possibly-missing/NaN score to a finite float in [0, 1].

        Stage-3 similarity can land slightly above 1.0, so clamp to keep
        confidence a true [0, 1] fraction for thresholds and the UI.
        """
        if MetaHarmonizerAdapter._is_missing(value):
            return 0.0
        try:
            f = float(value)
        except (TypeError, ValueError):
            return 0.0
        if math.isnan(f) or math.isinf(f):
            return 0.0
        return max(0.0, min(1.0, f))

    @staticmethod
    def _to_dashboard_row(raw: dict[str, Any]) -> dict[str, Any]:
        """Map one upstream row dict to the dashboard's expected shape."""
        match1 = raw.get("match1")
        matched_field = None if MetaHarmonizerAdapter._is_missing(match1) else str(match1)
        confidence = MetaHarmonizerAdapter._to_score(raw.get("match1_score"))

        alternatives = []
        for i in range(2, 6):
            m = raw.get(f"match{i}")
            if MetaHarmonizerAdapter._is_missing(m):
                continue
            alternatives.append(
                {
                    "field": str(m),
                    "score": round(
                        MetaHarmonizerAdapter._to_score(raw.get(f"match{i}_score")), 4
                    ),
                    "method": str(raw.get("method", "")),
                }
            )

        stage_raw = raw.get("stage")
        stage = "unmapped" if MetaHarmonizerAdapter._is_missing(stage_raw) else str(stage_raw)
        if stage == "invalid":
            status = "rejected"
        elif confidence >= _auto_accept_threshold():
            status = "accepted"
        else:
            status = "pending"

        method_raw = raw.get("method", "")
        method = "" if MetaHarmonizerAdapter._is_missing(method_raw) else str(method_raw)

        query_raw = raw.get("query", "")
        query = "" if MetaHarmonizerAdapter._is_missing(query_raw) else str(query_raw)

        return {
            "raw_column": query,
            "matched_field": matched_field,
            "confidence_score": round(confidence, 4),
            "stage": stage,
            "method": method,
            "alternatives": alternatives,
            "status": status,
        }
