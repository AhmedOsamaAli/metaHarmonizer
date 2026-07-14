"""
MockEngineAdapter — deterministic, dependency-free engine for tests.

No torch, no internet, no model download. ``pytest`` should pick this
adapter by default by setting ``ENGINE_IMPL=mock`` in its fixtures, or
through FastAPI ``app.dependency_overrides[get_engine]``.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .types import EngineHealth


class MockEngineAdapter:
    """Returns plausible-shaped fake data in <1 ms per call."""

    name = "mock"

    def harmonize_schema(
        self,
        raw_df: pd.DataFrame,
        curated_df: pd.DataFrame,
        *,
        csv_path: str | None = None,
        target_schema: str | None = None,
    ) -> list[dict[str, Any]]:
        curated_cols = list(curated_df.columns) if curated_df is not None else []
        rows: list[dict[str, Any]] = []
        for col in raw_df.columns:
            guess = col.lower()
            # Prefer a curated column that contains the same first letter — cheap heuristic
            match = next(
                (c for c in curated_cols if c.lower().startswith(guess[:2])),
                guess,
            )
            rows.append(
                {
                    "raw_column": col,
                    "matched_field": match,
                    "confidence_score": 0.95,
                    "stage": "stage1",
                    "method": "mock_exact",
                    "alternatives": [
                        {"field": f"alt_{i}", "score": round(0.9 - 0.1 * i, 3), "method": "mock"}
                        for i in range(1, 4)
                    ],
                    "status": "accepted",
                }
            )
        return rows

    def map_values(
        self,
        raw_df: pd.DataFrame,
        schema_mappings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for m in schema_mappings:
            col = m.get("raw_column")
            field = m.get("matched_field")
            if not col or not field or col not in raw_df.columns:
                continue
            for val in raw_df[col].dropna().unique()[:5]:
                results.append(
                    {
                        "field_name": field,
                        "raw_value": str(val),
                        "ontology_term": str(val).title(),
                        "ontology_id": f"MOCK:{abs(hash(str(val))) % 10000:04d}",
                        "confidence_score": 0.99,
                        "status": "accepted",
                    }
                )
        return results

    def llm_match(self, csv_path: str, raw_column: str) -> list[dict[str, Any]]:
        return [
            {
                "field": f"mock_{raw_column.lower()}",
                "confidence": 0.88,
                "reasoning": "mock adapter — no real LLM call",
            }
        ]

    def pre_warm(self) -> None:
        # Nothing to warm.
        return None

    def health(self) -> EngineHealth:
        return EngineHealth(
            ok=True,
            name=self.name,
            version="mock-1.0",
            loaded_models=[],
        )
