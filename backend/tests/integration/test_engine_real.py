"""Real-engine integration test — runs the actual metaharmonizer engine.

Unlike the unit/contract suite (which uses the deterministic MockEngineAdapter),
this exercises the *real* upstream engine end-to-end on a tiny CSV: schema
mapping over the bundled cBioPortal target preset. It needs the engine wheel
installed (and, on a cold machine, a one-time embedding-model download), so it
is opt-in — set ``RUN_REAL_ENGINE=1`` to run it (staging / nightly), and it is
skipped everywhere else so the fast suite stays hermetic.
"""

from __future__ import annotations

import os

import pandas as pd
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_REAL_ENGINE") != "1",
    reason="real engine test is opt-in (set RUN_REAL_ENGINE=1)",
)


@pytest.fixture
def real_engine():
    try:
        from app.engine_adapter.metaharmonizer_impl import MetaHarmonizerAdapter
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"metaharmonizer engine unavailable: {exc}")
    return MetaHarmonizerAdapter(mode="manual")


def test_real_schema_mapping(real_engine, tmp_path):
    raw = pd.DataFrame(
        {
            "AGE": [61, 47, 55],
            "Person Gender": ["Male", "Female", "Male"],
            "OS_STATUS": ["1:DECEASED", "0:LIVING", "1:DECEASED"],
        }
    )
    csv_path = tmp_path / "study.csv"
    raw.to_csv(csv_path, index=False)

    rows = real_engine.harmonize_schema(raw, curated_df=None, csv_path=str(csv_path))

    # Every raw column comes back, each with a mapping decision from a real stage.
    assert {r["raw_column"] for r in rows} == set(raw.columns)
    for r in rows:
        assert 0.0 <= float(r["confidence_score"]) <= 1.0
        assert r["stage"] in {"stage1", "stage2", "stage3", "stage4", "unmapped", "invalid"}
