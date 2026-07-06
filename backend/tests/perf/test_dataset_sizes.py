"""Dataset-size performance smoke for the engine adapter.

Uses the dependency-free MockEngineAdapter so it runs anywhere (CI included)
without Postgres/Redis/torch. The point is not to benchmark the real engine but
to prove the app-side data path scales linearly and doesn't blow up on wide or
tall inputs — a cheap guard before the real load tests run against a live stack.
"""

from __future__ import annotations

import time

import pandas as pd
import pytest

from app.engine_adapter.mock_impl import MockEngineAdapter


def _wide_frame(n_cols: int, n_rows: int = 5) -> pd.DataFrame:
    return pd.DataFrame(
        {f"col_{i}": [f"v{i}_{r}" for r in range(n_rows)] for i in range(n_cols)}
    )


@pytest.mark.parametrize("n_cols", [10, 200, 1000])
def test_schema_mapping_scales_with_columns(n_cols: int) -> None:
    engine = MockEngineAdapter()
    raw = _wide_frame(n_cols)
    curated = pd.DataFrame({"age": [], "sex": [], "sample_type": []})

    start = time.perf_counter()
    rows = engine.harmonize_schema(raw, curated)
    elapsed = time.perf_counter() - start

    # One mapping row per raw column, order preserved.
    assert len(rows) == n_cols
    assert [r["raw_column"] for r in rows] == list(raw.columns)
    # Generous ceiling — flags a pathological (super-linear) regression only.
    assert elapsed < 2.0, f"{n_cols} cols took {elapsed:.3f}s"


@pytest.mark.parametrize("n_rows", [100, 10_000])
def test_value_mapping_scales_with_rows(n_rows: int) -> None:
    engine = MockEngineAdapter()
    raw = pd.DataFrame({"SEX": (["Male", "Female"] * (n_rows // 2))[:n_rows]})
    mappings = [{"raw_column": "SEX", "matched_field": "sex"}]

    start = time.perf_counter()
    results = engine.map_values(raw, mappings)
    elapsed = time.perf_counter() - start

    # Value mapping de-duplicates, so the row count stays bounded regardless of size.
    assert results and all(r["field_name"] == "sex" for r in results)
    assert elapsed < 2.0, f"{n_rows} rows took {elapsed:.3f}s"
