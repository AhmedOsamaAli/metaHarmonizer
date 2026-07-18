"""Active-learning review ordering (G7).

Surfaces the mappings that actually need a human and keeps look-alikes together
so a curator can clear a whole group in one batch action. This is **queue
ordering only** — it never changes, hides, or auto-accepts a mapping.

Design (chosen over classic margin-sampling/diversity, which scatters the most-
different item next to maximize a *model's* information gain — the wrong goal
for a human reviewer):

  - **Risky first:** groups are ordered by their riskiest look-alike, so the
    least-certain sets are reviewed first while attention is fresh.
  - **Group similar:** mappings the engine sent to the same target field are
    grouped and kept *adjacent*, so a curator can batch-accept/reject the whole
    look-alike set in one motion instead of re-loading context per row.
  - **Stable position:** a group's rank comes from its riskiest member across
    *all* statuses, so accepting or rejecting one member never pushes the group
    down — the remaining look-alikes stay put and the curator finishes batching
    the set from the same place. A group leaves the queue only once every member
    is decided.
  - **Per-study / cross-curator:** the queue is one study's *pending* mappings;
    cleared decisions drop out and the next risky group surfaces.

Ordering only — nothing is changed, hidden, or auto-accepted.

Pure functions — no DB, no engine — so the ordering is fully testable.
"""

from __future__ import annotations

from typing import Any

# Mappings at/above this confidence are in the auto-accept band. The queue still
# includes them (nothing is hidden), but the risky ones lead.
SAFE_CONFIDENCE = 0.90


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

    # A group's rank comes from its riskiest look-alike across *all* statuses
    # (pending or already decided), so the group holds its position while the
    # curator works through it — accepting or rejecting one member never pushes
    # the group down, and the remaining look-alikes stay together for batch
    # review. (Position is stable; only the decided rows drop out.)
    group_all_min: dict[str, float] = {}
    for m in mappings:
        key = _group_key(m)
        c = _confidence(m)
        if key not in group_all_min or c < group_all_min[key]:
            group_all_min[key] = c

    groups: dict[str, list[dict[str, Any]]] = {}
    for m in pending:
        groups.setdefault(_group_key(m), []).append(m)

    # Riskiest group first (by its overall riskiest member); ties by key for
    # determinism. ``__unmapped__`` members are ~0 confidence, so they lead.
    ordered_keys = sorted(groups, key=lambda k: (group_all_min[k], k))

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
                    "group_min_confidence": round(group_all_min[key], 4),
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
    for m in queue:
        groups[m["group_key"]] = groups.get(m["group_key"], 0) + 1
        if _confidence(m) < SAFE_CONFIDENCE:
            risky += 1
    return {
        "pending": len(queue),
        "groups": len(groups),
        "batchable_groups": sum(1 for n in groups.values() if n > 1),
        "risky": risky,
    }
