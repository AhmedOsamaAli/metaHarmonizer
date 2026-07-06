"""
MetaHarmonizerAdapter — wraps the upstream pip-installable
``metaharmonizer`` package (https://github.com/shbrief/MetaHarmonizer).

THIS IS THE ONLY FILE IN THE PROJECT ALLOWED TO ``import metaharmonizer``.
The pre-commit hook ``scripts/check_engine_boundary.py`` enforces that.

To enable this adapter:

  1. Add the dependency (commit-pinned) to ``backend/requirements.txt``::

       metaharmonizer @ git+https://github.com/shbrief/MetaHarmonizer@<sha>

  2. ``pip install -r backend/requirements.txt``
  3. Set ``ENGINE_IMPL=metaharmonizer`` in the environment.

Until step 1 is done this module raises a clear error on first use; the
default ``VendoredAdapter`` keeps the app running.
"""

from __future__ import annotations

import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from .types import EngineHealth


_INSTALL_HINT = (
    "The 'metaharmonizer' package is not installed. Add\n"
    "  metaharmonizer @ git+https://github.com/shbrief/MetaHarmonizer@<sha>\n"
    "to backend/requirements.txt, then `pip install -r backend/requirements.txt`."
)

# Upstream looks for schema files (ncit_descendants.json, field_value_dict.json,
# curated_fields*.csv) under ``$METAHARMONIZER_DATA_DIR/schema/``. If the host
# hasn't set the env var, fall back to the dashboard-owned copy at
# ``backend/data/`` so a fresh checkout works without manual config.
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
        # Mode is "auto" (LLM enabled when GEMINI_API_KEY present) or "manual".
        if mode is None:
            mode = "auto" if os.getenv("GEMINI_API_KEY") else "manual"
        self._mode = mode
        self._top_k = top_k
        # Target schema preset the engine maps against. Default "cbio" (the
        # 33-field cBioPortal preset bundled in engine >=0.4.0) — the engine's
        # own default changed to "gdc" (736 fields), so we pin it explicitly to
        # keep the dashboard's cBioPortal behaviour. Override via env if needed.
        self._schema = os.getenv("ENGINE_TARGET_SCHEMA", "cbio")

    # ------------------------------------------------------------------
    @lru_cache(maxsize=8)
    def _engine_for(self, csv_path: str):
        pkg = _require_pkg()
        # Install perf patches (shared model + persistent NCI cache) before the
        # first engine is constructed so every study benefits. Idempotent.
        from . import _perf

        _perf.install_patches()
        # Upstream layout (engine >=0.4.0): SchemaMapEngine(input_path, schema,
        # *, top_k, mode, ...). Args renamed from 0.3.0 (clinical_data_path ->
        # input_path) and a target-schema preset added. Adjust here, never in
        # routers.
        SchemaMapEngine = pkg.SchemaMapEngine  # type: ignore[attr-defined]
        return SchemaMapEngine(
            csv_path,
            self._schema,
            mode=self._mode,
            top_k=self._top_k,
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
    ) -> list[dict[str, Any]]:
        if not csv_path:
            raise ValueError("metaharmonizer adapter requires csv_path")
        engine = self._engine_for(csv_path)
        raw = engine.run_schema_mapping()
        # Persist any new NCI EVS lookups so the next study (and the next
        # process) reuses them instead of re-hitting the network.
        from . import _perf

        _perf.save_nci_cache()
        return [self._to_dashboard_row(r) for r in raw.to_dict(orient="records")]

    def map_values(
        self,
        raw_df: pd.DataFrame,
        schema_mappings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        # Value-to-ontology mapping (F-11). For the categories the engine ships
        # first-class (NCIt-disease, UBERON-bodysite, NCIt-treatment) and only
        # when the operator opts in (``ONTOLOGY_ENGINE=1``), route through the
        # upstream ``OntoMapEngine`` (FAISS over the ontology corpus). Every
        # other field — and any engine failure / missing corpus — falls back to
        # the dashboard's curated dictionary so behaviour is unchanged by
        # default and never breaks. EFO / HANCESTRO are intentionally NOT here:
        # they need engine-team support (registry root / new category).
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
        # engine >=0.4.0: LLMMatcher is no longer top-level; it lives in the
        # schema-mapper stage-4 matchers module.
        try:
            LLMMatcher = pkg.LLMMatcher  # type: ignore[attr-defined]
        except AttributeError:
            from metaharmonizer.models.schema_mapper.matchers.stage4_matchers import (
                LLMMatcher,
            )
        engine = self._engine_for(csv_path)
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
        # Warm the NCI EVS cache over a representative sample so the FIRST real
        # upload doesn't pay the cold-cache network cost (~90s of rate-limited
        # API calls). Runs once; results persist to disk across restarts.
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
        # backend/app/engine_adapter/metaharmonizer_impl.py → repo root is
        # parents[3]; the curated metadata samples live under metadata_samples/.
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
        elif confidence >= 0.90:
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
