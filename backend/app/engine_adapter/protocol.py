"""
EngineProtocol — the contract our dashboard depends on.

Nothing outside ``backend/app/engine_adapter/`` is allowed to know which
concrete ML engine is in use. Routers, services, repositories and workers
talk to *this* interface only.

If you need a new capability from the engine, add a method here first,
then implement it in **every** adapter (vendored / mock / metaharmonizer).

See the package README (``backend/app/engine_adapter/README.md``)
for full guidance.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import pandas as pd

from .types import EngineHealth


@runtime_checkable
class EngineProtocol(Protocol):
    """
    The dashboard's view of any ML engine.

    All methods return JSON-serialisable dicts/lists so they can travel
    unchanged through FastAPI without an extra translation layer.
    Typed Pydantic DTOs live in ``types.py`` and are introduced gradually.
    """

    name: str
    """Human-readable adapter name, e.g. ``"vendored"``, ``"mock"``, ``"metaharmonizer"``."""

    # ------------------------------------------------------------------
    # Schema mapping (column-name → curated field)
    # ------------------------------------------------------------------
    def harmonize_schema(
        self,
        raw_df: pd.DataFrame,
        curated_df: pd.DataFrame,
        *,
        csv_path: str | None = None,
        target_schema: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Map every column in ``raw_df`` to a curated schema field.

        Returns a list of dashboard-shaped dicts with keys::

            raw_column, matched_field, confidence_score, stage,
            method, alternatives (list of {field, score, method}), status
        """
        ...

    # ------------------------------------------------------------------
    # Value-level ontology mapping (cell value → canonical term + ID)
    # ------------------------------------------------------------------
    def map_values(
        self,
        raw_df: pd.DataFrame,
        schema_mappings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Map raw cell values to canonical ontology terms (NCIT / UBERON / …).

        Returns dicts with keys::

            field_name, raw_value, ontology_term, ontology_id,
            confidence_score, status
        """
        ...

    # ------------------------------------------------------------------
    # On-demand LLM (Stage 4) — single column
    # ------------------------------------------------------------------
    def llm_match(self, csv_path: str, raw_column: str) -> list[dict[str, Any]]:
        """
        Ask the engine's LLM matcher for suggestions on one column.

        Returns dicts with keys ``field``, ``confidence``, ``reasoning``.
        May raise ``RuntimeError`` if the LLM is not configured
        (e.g. missing ``GEMINI_API_KEY``).
        """
        ...

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def pre_warm(self) -> None:
        """
        Load heavy resources (embeddings model, dictionaries, caches)
        before the first user request. Safe to call multiple times.
        """
        ...

    def health(self) -> EngineHealth:
        """Report engine readiness, version and loaded models."""
        ...
