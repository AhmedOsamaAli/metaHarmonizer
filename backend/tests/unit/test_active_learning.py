"""Unit tests for the active-learning review ordering (G7).

Pure functions — no DB, no engine — so these run in any venv. They assert the
two product decisions: risky-first ordering and grouping look-alikes together
(NOT diversity/scatter), and that the queue re-ranks as decisions are cleared.
"""

from __future__ import annotations

from app.services import active_learning as al


def _m(col, field, conf, status="pending"):
    return {
        "raw_column": col,
        "matched_field": field,
        "curator_field": None,
        "confidence_score": conf,
        "status": status,
    }


def test_only_pending_in_queue():
    mappings = [
        _m("a", "sex", 0.4),
        _m("b", "age", 0.5, status="accepted"),
        _m("c", "race", 0.6, status="rejected"),
    ]
    queue = al.build_review_queue(mappings)
    assert [m["raw_column"] for m in queue] == ["a"]


def test_risky_groups_lead():
    mappings = [
        _m("gender", "sex", 0.98),  # safe group
        _m("tumor_site_1", "body_site", 0.55),  # risky group
        _m("tumor_site_2", "body_site", 0.60),
    ]
    queue = al.build_review_queue(mappings)
    # The risky body_site group (min 0.55) comes before the safe sex group.
    assert queue[0]["group_key"] == "body_site"
    assert queue[-1]["group_key"] == "sex"


def test_lookalikes_are_adjacent_and_grouped():
    # Five columns the engine all sent to BODY_SITE, interleaved with others.
    mappings = [
        _m("site_a", "body_site", 0.61),
        _m("age_col", "age", 0.62),
        _m("site_b", "body_site", 0.60),
        _m("site_c", "body_site", 0.63),
        _m("sex_col", "sex", 0.64),
        _m("site_d", "body_site", 0.59),
        _m("site_e", "body_site", 0.58),
    ]
    queue = al.build_review_queue(mappings)
    # All body_site rows must be contiguous (NOT scattered for diversity).
    keys = [m["group_key"] for m in queue]
    first = keys.index("body_site")
    last = len(keys) - 1 - keys[::-1].index("body_site")
    body_site_run = keys[first : last + 1]
    assert all(k == "body_site" for k in body_site_run)
    # And the group carries its size so the UI can offer batch accept/reject.
    body = [m for m in queue if m["group_key"] == "body_site"]
    assert all(m["group_size"] == 5 for m in body)


def test_unmapped_columns_group_first():
    mappings = [
        _m("known", "sex", 0.30),
        {"raw_column": "mystery", "matched_field": None, "curator_field": None,
         "confidence_score": None, "status": "pending"},
    ]
    queue = al.build_review_queue(mappings)
    assert queue[0]["group_key"] == "__unmapped__"


def test_curator_field_overrides_grouping():
    # A curator edit (curator_field) regroups the mapping under the new target.
    m = _m("col", "wrong_field", 0.5)
    m["curator_field"] = "RIGHT_FIELD"
    queue = al.build_review_queue([m])
    assert queue[0]["group_key"] == "right_field"


def test_queue_reranks_as_decisions_clear():
    # Per-study/per-curator: clearing the risky group surfaces the next one.
    mappings = [
        _m("site_1", "body_site", 0.55),
        _m("site_2", "body_site", 0.56),
        _m("dx_1", "disease", 0.70),
    ]
    q1 = al.build_review_queue(mappings)
    assert q1[0]["group_key"] == "body_site"
    # Curator batch-accepts the body_site group.
    for m in mappings:
        if m["matched_field"] == "body_site":
            m["status"] = "accepted"
    q2 = al.build_review_queue(mappings)
    assert [m["raw_column"] for m in q2] == ["dx_1"]
    assert q2[0]["group_key"] == "disease"


def test_queue_stats():
    mappings = [
        _m("s1", "body_site", 0.55),
        _m("s2", "body_site", 0.60),
        _m("only", "sex", 0.95),  # safe, singleton
    ]
    queue = al.build_review_queue(mappings)
    stats = al.queue_stats(queue)
    assert stats["pending"] == 3
    assert stats["groups"] == 2
    assert stats["batchable_groups"] == 1  # body_site has 2 members
    assert stats["risky"] == 2  # the two below 0.90


def test_accepted_lookalikes_deprioritize_remaining():
    # The curator has accepted 3 of a body_site look-alike group; the remaining
    # pending look-alike should sink below an untouched, genuinely-new risky
    # group even at similar raw confidence (G7 feedback re-rank).
    mappings = [
        _m("site_1", "body_site", 0.55, status="accepted"),
        _m("site_2", "body_site", 0.55, status="accepted"),
        _m("site_3", "body_site", 0.55, status="accepted"),
        _m("site_4", "body_site", 0.55),  # pending near-duplicate of accepted
        _m("new_dx", "disease", 0.58),  # untouched, genuinely new
    ]
    queue = al.build_review_queue(mappings)
    assert queue[0]["group_key"] == "disease"  # genuinely-new case leads
    assert queue[-1]["group_key"] == "body_site"  # settled look-alike sinks
    site = next(m for m in queue if m["group_key"] == "body_site")
    assert site["group_accepted"] == 3


def test_no_feedback_ordering_is_unchanged():
    # With no acceptances, the penalty is zero — ordering is pure risky-first.
    mappings = [
        _m("dx", "disease", 0.58),
        _m("site", "body_site", 0.55),
    ]
    queue = al.build_review_queue(mappings)
    assert queue[0]["group_key"] == "body_site"  # 0.55 leads 0.58
    assert all(m["group_accepted"] == 0 for m in queue)


def test_deprioritized_groups_stat():
    mappings = [
        _m("s1", "body_site", 0.55, status="accepted"),
        _m("s2", "body_site", 0.55),  # remaining look-alike (pending)
        _m("new", "disease", 0.60),
    ]
    stats = al.queue_stats(al.build_review_queue(mappings))
    assert stats["deprioritized_groups"] == 1  # body_site partly accepted
