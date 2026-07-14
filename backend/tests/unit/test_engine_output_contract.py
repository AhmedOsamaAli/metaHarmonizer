"""Engine output-column contract test (F-11 safeguard).

The dashboard depends on the upstream ``metaharmonizer`` package emitting a
stable set of *output columns* from its schema-mapping call. We promised the
engine team that any rename here is a breaking change they tag, and that our
adapter absorbs it in ONE place (``metaharmonizer_impl._to_dashboard_row``).

That promise is only real if a rename fails loudly instead of silently
returning empty mappings. These tests are that tripwire:

1. ``test_dashboard_row_reads_contract_columns`` pins the exact upstream column
   names the adapter reads, using a synthetic row. Runs anywhere pandas is
   importable; no engine, no network.
2. ``test_engine_schema_output_has_contract_columns`` runs the *real* engine on
   a tiny CSV and asserts the output frame still carries the contract columns.
   Skips where the heavy ``metaharmonizer`` package isn't installed (the
   lightweight test venv); runs in the full engine env / CI-with-engine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pandas")
import pandas as pd  # noqa: E402

# The schema-mapping output columns the adapter reads. Single source of truth
# for the contract; mirrors metaharmonizer_impl._to_dashboard_row + the
# alternatives loop.
#
# HARD contract — always present in every result frame: the engine always
# emits a query, a stage, a method, and a top-1 candidate + score.
CONTRACT_REQUIRED_COLUMNS = {"query", "stage", "method", "match1", "match1_score"}
# OPTIONAL-but-PAIRED — match2..match5 only appear when that many candidates
# exist (a tiny input yields fewer). When match{i} is present, match{i}_score
# must be too. The adapter loops 2..5 and skips missing ones, so this pairing
# is the real invariant. ``match{i}_source`` is emitted upstream but not
# consumed today, so it is not required here.
CONTRACT_OPTIONAL_MATCH_RANGE = range(2, 6)


def _synthetic_upstream_row() -> dict:
    """One row shaped exactly like upstream ``run_schema_mapping()`` output."""
    row = {
        "query": "gender",
        "stage": "stage1",
        "method": "std_exact",
        "match1": "SEX",
        "match1_score": 0.98,
        "match1_source": "curated",
        "match2": "GENDER",
        "match2_score": 0.71,
        "match2_source": "ontology",
    }
    for i in range(3, 6):
        row[f"match{i}"] = None
        row[f"match{i}_score"] = None
        row[f"match{i}_source"] = None
    return row


def test_dashboard_row_reads_contract_columns():
    """The adapter must read the canonical upstream column names.

    If someone changes ``_to_dashboard_row`` to read different keys, this row
    (built with the contract names) stops translating correctly and the test
    fails — surfacing the boundary drift.
    """
    from app.engine_adapter.metaharmonizer_impl import MetaHarmonizerAdapter as A

    out = A._to_dashboard_row(_synthetic_upstream_row())

    assert out["raw_column"] == "gender"  # from `query`
    assert out["matched_field"] == "SEX"  # from `match1`
    assert out["confidence_score"] == 0.98  # from `match1_score`
    assert out["stage"] == "stage1"  # passed through from `stage`
    assert out["method"] == "std_exact"  # from `method`
    # The single non-empty alternative comes from match2/match2_score.
    assert out["alternatives"] == [
        {"field": "GENDER", "score": 0.71, "method": "std_exact"}
    ]


def test_to_dashboard_row_survives_extra_upstream_columns():
    """Extra/unknown upstream columns must not break translation.

    The engine team is free to ADD columns without coordination; only renames
    of the contract columns are breaking. A new column must pass through
    harmlessly.
    """
    from app.engine_adapter.metaharmonizer_impl import MetaHarmonizerAdapter as A

    row = _synthetic_upstream_row()
    row["some_new_upstream_column"] = "ignore me"

    out = A._to_dashboard_row(row)
    assert out["matched_field"] == "SEX"


def test_engine_schema_output_has_contract_columns(tmp_path):
    """Run the real engine and assert the contract columns are present.

    Skips when the heavy upstream package isn't installed. This is the tripwire
    that catches an actual upstream output-column rename. Uses the bundled
    multi-column sample so the engine produces the full match1..match5 fan-out
    (a 2-column input only yields match1).
    """
    pytest.importorskip("metaharmonizer")

    from app.engine_adapter.metaharmonizer_impl import MetaHarmonizerAdapter

    # A real, wide sample yields multiple candidates per column. Fall back to a
    # synthesised wide frame if the bundled sample has moved.
    sample = (
        Path(__file__).resolve().parents[3] / "metadata_samples" / "new_meta.csv"
    )
    if sample.exists():
        csv = str(sample)
    else:
        csv_path = tmp_path / "wide.csv"
        pd.DataFrame(
            {
                "gender": ["male", "female"],
                "age": ["57", "61"],
                "tissue": ["lung", "liver"],
                "stage": ["III", "II"],
                "ethnicity": ["dutch", "han"],
            }
        ).to_csv(csv_path, index=False)
        csv = str(csv_path)

    from app.engine_adapter import _schema_registry

    adapter = MetaHarmonizerAdapter(mode="manual")
    engine = adapter._engine_for(csv, _schema_registry.default_key())
    frame = engine.run_schema_mapping()
    cols = set(frame.columns)

    # 1. Required columns are always present.
    missing = CONTRACT_REQUIRED_COLUMNS - cols
    assert not missing, (
        "Upstream metaharmonizer schema-mapping output is missing REQUIRED "
        f"contract columns {sorted(missing)}. This is a BREAKING engine change "
        "— update metaharmonizer_impl._to_dashboard_row (the one translation "
        "point) and this contract."
    )

    # 2. Optional match{i}/match{i}_score columns must come as a pair when present.
    for i in CONTRACT_OPTIONAL_MATCH_RANGE:
        has_match = f"match{i}" in cols
        has_score = f"match{i}_score" in cols
        assert has_match == has_score, (
            f"Upstream emits match{i}={has_match} but match{i}_score={has_score}; "
            "the adapter reads them as a pair. Update the adapter + this contract."
        )
