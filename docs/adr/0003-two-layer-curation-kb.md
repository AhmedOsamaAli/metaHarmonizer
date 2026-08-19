# ADR 0003 — Two-Layer Curation Knowledge Base (learned decisions)

**Date:** 2026-06-21
**Status:** Accepted — implemented; items marked **OPEN** remain governance
questions for the curation team
**Deciders:** Dashboard maintainers · curation team (Sehyun) for governance

> Implements two-stage approval and the tiered knowledge base behind active
> learning. Sections marked **OPEN** need a one-line answer from the curation
> team before the related behavior is changed.

## Context

Today every curation decision is **study-scoped**. A mapping accepted in study A
has no effect on study B; initial status comes purely from confidence thresholds
(`THRESHOLD_AUTO_ACCEPT = 0.90`) with no lookup against past decisions. There is
no learned-mapping table. Verified in code:

- `mappings` / `ontology_mappings` rows are keyed and queried by `study_id` only.
- `harmonizer.run_ontology_mapping()` assigns status from the fresh score; it
  never consults prior curator decisions.
- The learning signal already exists: `audit_events` records `accept` / `reject`
  / `edit` with `actor_id`, `old_value`, `new_value`.

Curators re-decide the same obvious mappings on every study. The mentor's steer is
to **do the heavy lifting for curators** — a learned-decision KB removes that
repetition while keeping humans in control (Q10: *nothing is auto-merged*).

## Decision

Introduce a single scoped table, `learned_decision`, with two logical layers
(**personal** per-curator, **shared** admin-promoted), a lookup applied during
harmonize, and a two-stage promotion flow.

### Data model

```
learned_decision
  id              PK
  scope           'personal' | 'shared'
  owner_id        FK users.id    (NULL when scope='shared')
  kind            'schema' | 'ontology'
  source_key      normalized lookup key:
                    schema   -> normalized raw column name
                    ontology -> 'field_name::normalized_raw_value'
  decision        'accept' | 'reject'
  target_field    canonical field      (schema; NULL for reject)
  target_term     ontology term label  (ontology)
  target_id       ontology id          (ontology)
  origin_study_id where first decided
  support_count   distinct (curator, study) confirmations  -- promotion analytics
  promoted_by     FK users.id          (shared only)
  created_at / updated_at
  UNIQUE (scope, owner_id, kind, source_key)
```

- **Personal layer** = `scope='personal'`, read by the owning curator.
- **Shared layer** = `scope='shared'`, read by everyone; `owner_id` NULL.
- Normalization (lowercase, trim, collapse whitespace/punctuation) is shared by
  the writer and the lookup so keys match across studies.

### Write path (capturing a decision)

On accept/reject/edit the curator chooses how durable the decision is:

- **[Just this study]** — current behaviour; nothing written to the KB.
- **[Remember for my future studies]** — upsert a `scope='personal'` row for the
  acting curator, bump `support_count`.

A per-curator profile default (“always remember my decisions”) can pre-select the
second option so it’s one click. **OPEN:** confirm curators want a global default
vs per-decision choice.

### Read path (applying the KB during harmonize)

After the engine produces mappings, look up each row against the KB in precedence
order **personal → shared**. On a hit:

- **OPEN (behaviour):** **(a)** auto-apply silently, or **(b)** pre-apply the
  status but keep the row visible and flagged for confirmation.
  - _Recommendation: **(b)** pre-apply + flag, never silent_ — preserves the
    audit trail and curator control; active-learning re-ranking already surfaces
    the genuinely uncertain rows, so flagged auto-applies don't add noise.
- Every KB-driven application writes an audit row
  (`action='kb_apply'`, details `{source: personal|shared, learned_decision_id}`)
  so it is fully traceable and we can later measure curator-time saved.

### Promotion (two-stage, Q10)

1. Curator confirms a mapping (personal layer) — stage 1.
2. Admin **review queue** surfaces high-agreement candidates with analytics
   (`support_count`, distinct curators, agreement rate). Admin **promotes** →
   inserts/updates a `scope='shared'` row (`promoted_by`), or **rejects**.
3. Federation imports always require local approval (already Q10).

**Precedence when personal and shared disagree:** _proposal — shared is the team
baseline; a curator's personal row overrides it for that curator only._

**OPEN (governance), for the curation team:**
- On promote, does the shared entry **replace** each curator's personal row or
  **coexist** (personal overrides)? _Proposal: coexist + personal overrides._
- Is a **rejection** visible to the proposing curator?
- **Multi-admin:** one shared review queue, or partitioned per admin?
  _Needs a brief best-practice look at review-queue ownership patterns._

### Scope & boundaries

- Active learning (Sprint 6) re-ranks the **review queue** only; KB membership is
  governed by this ADR's two-stage approval, independent of AL ranking.
- This KB is **app-owned** and distinct from the **engine's ontology KB**
  (FAISS/SQLite `OntoMapEngine`, F-11 engine-owned). No overlap.

## Consequences

**Positive**
- Curators stop re-deciding the same obvious mappings; the system gets smarter the
  more it's used, while Q10 keeps every merge human-approved.
- Pure additive table + one lookup; no change to the engine boundary or existing
  per-study contracts. Auditable end to end.
- `support_count` gives admins real promotion analytics instead of guesswork.

**Negative**
- A wrong personal entry could silently pre-apply across a curator's studies —
  mitigated by recommended behaviour (b) (flag, not silent) and the audit trail.
- Normalization choices affect hit rate; needs a small, well-tested normalizer.
- One more table + a promotion UI surface to maintain.

## Status of build

| Step                                                      | State    |
| --------------------------------------------------------- | -------- |
| `learned_decision` table + migration                      | Not started |
| Write path: [Just this study] / [Remember] on decisions   | Not started |
| Read path: KB lookup during harmonize + `kb_apply` audit  | Not started |
| Admin promotion queue + analytics                         | Not started |
| OPEN questions confirmed with curation team                | Pending  |
