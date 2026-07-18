"""Active-learning review ordering (G7).

Surfaces the mappings that actually need a human and keeps look-alikes together
so a curator can clear a whole group in one batch action. This is **queue
ordering only** — it never changes, hides, or auto-accepts a mapping.

Design — a human-tuned take on margin-sampling (classic margin-sampling
optimizes a *model's* information gain by showing the most-different item next,
the wrong goal for a human reviewer, so we keep look-alikes together and let
curator feedback drive the re-rank instead):

  - **Risky first:** order by confidence ascending, so the least-certain
    mappings are reviewed first while attention is fresh.
  - **Group similar:** mappings the engine sent to the same target field are
    grouped and kept *adjacent*, so a curator can batch-accept/reject the whole
    look-alike set in one motion instead of re-loading context per row.
  - **Feedback-aware re-rank:** each prior acceptance of a look-alike nudges the
    remaining pending near-duplicates down the queue, so once the curator has
    validated a pattern the engine stops re-surfacing it and moves to genuinely
    new cases. Cross-curator + per-study: feedback is every accepted mapping on
    the study, so curators sharing a study benefit from each other's decisions.
  - **Per-study:** the queue is one study's *pending* mappings, so cleared
    decisions drop out and the next risky group surfaces.

Ordering only — nothing is changed, hidden, or auto-accepted.

Pure functions — no DB, no engine — so the ordering is fully testable.
"""

from __future__ import annotations

from typing import Any

# Mappings at/above this confidence are in the auto-accept band. The queue still
# includes them (nothing is hidden), but the risky ones lead.
SAFE_CONFIDENCE = 0.90

# Feedback re-rank (G7): each prior acceptance of a look-alike (same suggested
# target) nudges the remaining pending look-alikes down the queue — once the
# curator has validated a pattern, near-duplicates are lower-value to review
# ("small penalty when a candidate resembles a recent acceptance"). Capped so a
# heavily-accepted group sinks but is never hidden.
AL_ACCEPT_PENALTY = 0.15
AL_PENALTY_CAP = 0.60


def _confidence(m: dict[str, Any]) -> float:
    c = m.get("confidence_score")
    try:
        return float(c) if c is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _group_key(m: dict[str, Any]) -> str:
    """Items sharing a suggested target field form one batchable group.

    Falls back to ``__unmapped__`` so columns with no suggestion cluster
    together (they always need a manual decision and read best as a set).
    """
    target = m.get("curator_field") or m.get("matched_field")
    if not target:
        return "__unmapped__"
    return str(target).strip().lower()


def build_review_queue(mappings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the *pending* mappings, ordered risky-first and grouped.

    Each returned row is the original mapping dict plus:
      - ``group_key``  : the shared target (or ``__unmapped__``);
      - ``group_size`` : how many pending mappings share that group;
      - ``group_min_confidence`` : the group's lowest confidence (its risk).

    Groups are ordered by their riskiest member; within a group, by ascending
    confidence then column name (stable, predictable for keyboard review). The
    grouping keeps look-alikes adjacent so the existing batch accept/reject can
    clear them together.
    """
    pending = [m for m in mappings if m.get("status") == "pending"]

    # Cross-curator feedback for this study: how many mappings the team has
    # already ACCEPTED into each look-alike group. A prior acceptance marks a
    # validated pattern, so its remaining pending look-alikes are lower-value.
    accepted_by_group: dict[str, int] = {}
    for m in mappings:
        if m.get("status") == "accepted":
            key = _group_key(m)
            accepted_by_group[key] = accepted_by_group.get(key, 0) + 1

    groups: dict[str, list[dict[str, Any]]] = {}
    for m in pending:
        groups.setdefault(_group_key(m), []).append(m)

    group_min: dict[str, float] = {
        key: min(_confidence(m) for m in members) for key, members in groups.items()
    }

    def _accept_penalty(key: str) -> float:
        return min(AL_PENALTY_CAP, AL_ACCEPT_PENALTY * accepted_by_group.get(key, 0))

    # Riskiest group (lowest min confidence) first, but a group whose pattern the
    # curator has already accepted is nudged down by its acceptance penalty — so
    # genuinely-new risky cases surface ahead of near-duplicates of settled ones.
    # Ties by key for determinism. ``__unmapped__`` members are ~0 confidence.
    ordered_keys = sorted(groups, key=lambda k: (group_min[k] + _accept_penalty(k), k))

    out: list[dict[str, Any]] = []
    for key in ordered_keys:
        members = sorted(
            groups[key],
            key=lambda m: (_confidence(m), str(m.get("raw_column") or "")),
        )
        for m in members:
            out.append(
                {
                    **m,
                    "group_key": key,
                    "group_size": len(members),
                    "group_min_confidence": round(group_min[key], 4),
                    "group_accepted": accepted_by_group.get(key, 0),
                }
            )
    return out


def queue_stats(queue: list[dict[str, Any]]) -> dict[str, Any]:
    """Summary for the audit trail / UI: how the queue is shaped.

    ``batchable_groups`` counts groups with more than one pending member — where
    batch accept/reject saves the most time.
    """
    groups: dict[str, int] = {}
    risky = 0
    settled: set[str] = set()
    for m in queue:
        groups[m["group_key"]] = groups.get(m["group_key"], 0) + 1
        if _confidence(m) < SAFE_CONFIDENCE:
            risky += 1
        if m.get("group_accepted", 0) > 0:
            settled.add(m["group_key"])
    return {
        "pending": len(queue),
        "groups": len(groups),
        "batchable_groups": sum(1 for n in groups.values() if n > 1),
        "risky": risky,
        # Groups the curator has already partly accepted (their remaining
        # look-alikes were de-prioritized).
        "deprioritized_groups": len(settled),
    }
