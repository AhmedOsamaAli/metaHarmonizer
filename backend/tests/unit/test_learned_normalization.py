"""Clinical-safety: learned-KB value normalization must keep '+'/'-' so that
opposite statuses (ER+ vs ER-) never share a learned-decision key.

Regression guard for the ER+/ER- collision: ``normalize`` collapsed ``[\\s\\W_]+``,
which turned both "ER+" and "ER-" into "er".
"""
from __future__ import annotations

import pytest

from app.repositories import learned_decisions as ld


@pytest.mark.parametrize(
    "pos,neg",
    [
        ("ER+", "ER-"),
        ("PR+", "PR-"),
        ("HER2+", "HER2-"),
        ("O+", "O-"),          # blood type
    ],
)
def test_value_sign_is_preserved(pos: str, neg: str) -> None:
    assert ld.normalize_value(pos) != ld.normalize_value(neg)
    assert ld.ontology_key("receptor_status", pos) != ld.ontology_key("receptor_status", neg)


def test_value_sign_normalized_forms() -> None:
    assert ld.normalize_value("ER+") == "er+"
    assert ld.normalize_value("ER-") == "er-"


def test_value_still_collapses_whitespace_and_punctuation() -> None:
    # Non-sign punctuation / whitespace / underscore still collapse to one space.
    assert ld.normalize_value("Body_Site") == "body site"
    assert ld.normalize_value("Stage (IV)") == "stage iv"
    assert ld.normalize_value("  stool  ") == "stool"


def test_non_signed_values_unchanged_vs_old_behavior() -> None:
    # Values without '+'/'-' normalize identically to the schema normalizer,
    # so existing keys (e.g. body_site::stool) are unaffected.
    for v in ("stool", "blood", "primary tumor"):
        assert ld.normalize_value(v) == ld.normalize(v)


def test_schema_key_still_collapses_separators() -> None:
    # Column-name matching is unchanged: '-', '_', spaces are interchangeable.
    assert ld.schema_key("Body_Site") == ld.schema_key("body-site") == ld.schema_key("  body   site ")
