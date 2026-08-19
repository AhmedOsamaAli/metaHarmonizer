# ADR 0001 — Engine Adapter Pattern

**Date:** 2026-05-22  
**Status:** Accepted  
**Deciders:** Dashboard maintainers

## Context

The dashboard was built around a frozen copy of the `shbrief/MetaHarmonizer`
engine, vendored at `backend/engine/`. Routers and services reached into it
directly via `from src.*` imports.

Six weeks after vendoring, upstream had moved substantially ahead (full
ontology subsystem with FAISS, refreshed thresholds, packaging as a real
pip module, LLM extras). We had no clean way to pull those changes — every
file copy risked breaking 30+ import sites scattered across the app.

## Decision

Introduce an **engine adapter** at `backend/app/engine_adapter/` that:

1. Exposes a small `EngineProtocol` listing the methods our dashboard
   actually uses (`harmonize_schema`, `map_values`, `llm_match`,
   `pre_warm`, `health`).
2. Ships three implementations behind one `get_engine()` factory:
   - `VendoredAdapter` — wraps the current `backend/engine/` source copy.
   - `MockEngineAdapter` — deterministic, no torch, no network. For tests.
   - `MetaHarmonizerAdapter` — wraps the pip-installable upstream package.
3. Is selected at runtime by `ENGINE_IMPL=vendored|mock|metaharmonizer`.

Routers receive the adapter through FastAPI `Depends(get_engine)`. They
never import `metaharmonizer`, `src.*` or `engine.src.*`. A pre-commit
hook (`scripts/check_engine_boundary.py`) and the
`.github/workflows/engine-boundary.yml` workflow enforce the rule.

## Consequences

**Positive**

- Upstream upgrades become a one-line change in `requirements.txt`
  (or a SHA bump) plus, at most, a tweak to one translation function in
  `metaharmonizer_impl.py`.
- Tests run in milliseconds against `MockEngineAdapter`. No model
  download, no internet.
- We can A/B compare engines side-by-side (Phase-1 benchmark deliverable
  in the GSoC proposal) by instantiating two adapters and diffing their
  output.
- New contributors learn one small interface instead of the full upstream
  module tree.

**Negative**

- One extra indirection. ~250 lines of glue code we now own.
- We must keep all three adapters in step when adding a new
  capability — but this is automatic: a missing method fails type-check.

## Status of migration

| Step                                                         | State |
| ------------------------------------------------------------ | ----- |
| 1 — Create the seam, route through `Depends(get_engine)`     | Done  |
| 2 — `MockEngineAdapter`                                      | Done  |
| 3 — `MetaHarmonizerAdapter` + pinned `requirements.txt` line | Done  |
| 4 — Flip default to `metaharmonizer`                         | Done  |
| 5 — Delete `backend/engine/` and `backend/engine_upstream/`  | Done  |
| 6 — Pre-commit hook + CI workflow + this ADR                 | Done  |

Migration complete (2026-05-22). `VendoredAdapter` and the legacy
`backend/engine/` source tree have been removed; the only adapter
implementations remaining are `MetaHarmonizerAdapter` (default) and
`MockEngineAdapter` (tests). The schema files the upstream package
needs at runtime (`ncit_descendants.json`, `field_value_dict.json`,
optional alias dict) now live at `backend/data/schema/` and the
adapter auto-points `METAHARMONIZER_DATA_DIR` at them when the env
var is unset.

## Links

- [backend/app/engine_adapter/README.md](../../backend/app/engine_adapter/README.md) — developer guide
- Upstream engine: https://github.com/shbrief/MetaHarmonizer
