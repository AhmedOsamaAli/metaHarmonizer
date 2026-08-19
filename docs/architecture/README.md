# MetaHarmonizer — Architecture Review Dossier

> Principal-architect reverse-engineering of the MetaHarmonizer system, produced from source
> (code, Dockerfiles, Compose, Caddy, GitHub Actions, migrations, settings). This folder is the
> single entry point; deep dives and renderable diagrams are linked throughout.

**Contents**

1. [Executive Summary](#1-executive-summary)
2. [System Discovery Report](#2-system-discovery-report)
3. [Architecture Model (by layer)](#3-architecture-model-by-layer)
4. [Infrastructure Architecture](#4-infrastructure-architecture)
5. [Architecture Review](#5-architecture-review)
6. [Architecture Decision Records](#6-architecture-decision-records)
7. [Diagram assets](#7-diagram-assets)

**Companion deliverables**

- 🔧 [engine-system-design.md](engine-system-design.md) — the ML engine + adapter boundary (headline).
- 🖥️ [dashboard-system-design.md](dashboard-system-design.md) — the dashboard services (headline).
- 🧭 [workspace.dsl](workspace.dsl) — C4 model (Structurizr DSL: context, container, component, deployment).
- 🔷 [architecture.d2](architecture.d2) — full D2 system diagram.
- 📐 [architecture.drawio](architecture.drawio) — editable draw.io diagram for slides.

---

## 1. Executive Summary

**MetaHarmonizer Dashboard** is a curator-in-the-loop platform that automates the harmonization of
clinical/biomedical study metadata to a curated reference schema (cBioPortal / GDC / cMD presets) and
biomedical ontologies (NCIt, UBERON), then lets a human confirm before producing
**cBioPortal-compatible** exports. It is built for a bioinformatics curation team and doubles as a
GSoC engineering showcase.

**Shape.** A React SPA fronted by Caddy talks to a FastAPI backend that is strictly layered
(`routers → services → repositories → db`) with a single **engine-adapter boundary** isolating the ML
package. Long-running harmonization is offloaded to a job pipeline (in-thread in dev, **arq/Redis
workers** in prod) with **live WebSocket progress** via a Redis pub/sub bus. State lives in
**PostgreSQL 16**; **Redis 7** backs the queue, progress bus, rate-limiting, and idempotency. The same
engine is also exposed to LLM agents through an **MCP server**.

**Standout strengths.** (1) A CI-enforced engine-adapter boundary that makes ML upgrades cheap and
makes the whole system testable with a dependency-free mock; (2) first-class **reproducibility** —
every study is pinned to a schema version + ontology snapshot; (3) a mature **security & safety**
posture (JWT+refresh, RBAC, lockout, HIBP, CSP, rate-limit/idempotency, upload guards, append-only
audit); (4) a pragmatic **inline↔queue** job model that scales from a laptop to horizontal workers by
flipping one env var.

**Primary risks.** Single-node datastores (Postgres/Redis are SPOFs as configured), a large ~1.4 GB KB
bundle that must be seeded per environment, cold-start model loading, and reliance on external
vocabulary APIs (cached). None are architecture-breaking; all have clear remediation paths (Section 5).

---

## 2. System Discovery Report

**Purpose / domain.** Biomedical clinical-metadata curation. Turn messy study columns/values into a
canonical schema + ontology codes with confidence scoring and human review; export for cBioPortal.

**Major user journeys.** (a) Upload → harmonize → review mappings → export; (b) review value→ontology
mappings and search terms; (c) admin: manage users/roles, upload schema versions & alias dictionaries,
promote learned decisions, inspect the activity log; (d) agent: call harmonization tools over MCP.

### Component inventory

| Component | Responsibility | Technology | Depends on | Upstream | Downstream | Criticality |
|---|---|---|---|---|---|---|
| **SPA** | Curator UI: upload, review, quality, export, admin, activity | React 18, Vite, TypeScript, Tailwind, React Query, React Router, Recharts, framer-motion, Radix | Caddy/API | Curator | API | High |
| **Caddy** | Reverse proxy: SPA static + `/api/*` + WS; CSP/security headers; gzip; TLS (prod) | Caddy 2 | web_dist, API | SPA | API | High |
| **FastAPI API** | HTTP API, authz, orchestration, middleware | FastAPI, uvicorn, Pydantic, SQLAlchemy async | PG, Redis, engine, object store | Caddy/MCP | services→repos→db, engine | Critical |
| **Worker** | Runs harmonize jobs + cron (retention, nightly labeled export) | arq (Redis) | Redis, PG, engine | API (enqueue) | PG, engine | High |
| **Engine adapter** | Only importer of `metaharmonizer`; translation, target-schema resolution, perf patches | Python `Protocol` | metaharmonizer wheel | services/workers | engine + KB | Critical |
| **Engine** | Schema (4-stage) + value→ontology mapping | `metaharmonizer` 0.4.1, SentenceTransformers, FAISS, SQLite | KB bundle, Gemini, vocab APIs | adapter | KB | Critical |
| **PostgreSQL** | System of record (studies, mappings, audit, users, pins…) | Postgres 16, asyncpg | — | API/worker | — | Critical |
| **Redis** | Job queue, progress pub/sub, rate-limit, idempotency, WS tickets, cancel flags | Redis 7 | — | API/worker | — | High |
| **Object store** | Uploaded CSVs + generated exports | file:// volume or S3/R2 | — | API/worker | — | High |
| **KB bundle** | FAISS indexes + embedding model + ontology corpora | tar bundle → volumes | build_kb / kb-import | engine | — | High |
| **MCP server** | Harmonization as 3 agent tools | `mcp` FastMCP, stdio/SSE | engine adapter | LLM agents | engine | Medium |

**External integrations.** Gemini (Stage-4 LLM, optional), NCI EVS / OLS / UMLS (ontology lookups,
cached), Resend (email verify/reset; dev logs links), HaveIBeenPwned (breach check, fail-open), Sentry
(errors, optional), HuggingFace Hub (model source; offline in prod).

**Background / scheduled.** arq `harmonize_job`; cron **nightly labeled-dataset export** at 02:30
([arq_worker.py](../../backend/app/workers/arq_worker.py)); **retention** sweeps for uploads/exports/
revoked sessions ([workers/retention.py](../../backend/app/workers/retention.py),
[settings.py](../../backend/app/core/settings.py) `RETENTION_*`).

**Auth flow.** JWT access (15 m) + refresh cookie (30 d, httpOnly, Secure in HTTPS), email
verification, password reset, account lockout, HIBP, RBAC (curator/admin), admin approval for
untrusted domains, personal API tokens, one-time WS tickets; `AUTH_MODE=none` dev bypass.

**Observability / logging.** Structured logging + request-id + unified error envelope
([core/middleware.py](../../backend/app/core/middleware.py)); Prometheus golden-signal metrics at
admin-scoped `/metrics` ([core/metrics.py](../../backend/app/core/metrics.py)); Sentry
([core/sentry.py](../../backend/app/core/sentry.py)); `/healthz`, `/readyz`, `/health/engine`.

**Deployment.** Docker Compose — base (`postgres, redis, api, worker, caddy` + one-shot `web`,
`kb-import`) + dev override (bind-mounts, `--reload`, host ports, http Caddy) or prod overlay
(TLS Caddy, required secrets, `JOB_MODE=queue`, scalable workers). Non-Docker dev path via portable
Postgres/Redis ([scripts/dev_services.ps1](../../scripts/dev_services.ps1)).

---

## 3. Architecture Model (by layer)

- **Frontend** — React SPA (pages: Upload, MappingReview, OntologyReview, Quality, Export, Admin,
  Activity, Profile, auth); React Query data layer; served as static assets from `web_dist`.
- **API / gateway** — Caddy edge (routing, CSP, TLS) + FastAPI routers (Section 3.1 of the dashboard doc);
  middleware chain: request-id/error-envelope → security headers → Prometheus → rate-limit/idempotency
  → CORS.
- **Business logic** — services: `harmonizer`, `exporter`, `analytics`, `active_learning`,
  `learned_apply`, `linkml_gate`, `mapping_evaluation`, `schema_diff`, `federation`.
- **Data** — PostgreSQL 16 (async SQLAlchemy + Alembic migrations); repositories per aggregate;
  object store (file:// or S3/R2) for uploads/exports; KB volumes for FAISS/models/corpora.
- **Messaging** — Redis: arq job queue + pub/sub progress bus (+ rate-limit, idempotency, cancel
  flags, WS tickets). WebSocket carries live progress to browsers.
- **Infrastructure** — Docker Compose; one image for API+worker; Caddy reverse proxy; named volumes;
  internal network with only Caddy public in prod.
- **Observability** — Prometheus metrics, structured logs + request-id, Sentry, health/readiness.
- **Security** — JWT+refresh, RBAC, account lockout, HIBP, CSP + security headers, CORS allow-list,
  rate-limiting + idempotency, upload size/row guards, append-only audit, optimistic concurrency,
  Ed25519-signed federation exports.

---

## 4. Infrastructure Architecture

| Environment | Command | Topology notes |
|---|---|---|
| **Dev** | `docker compose up` (auto-loads override) or `make up` | Bind-mounts + `uvicorn --reload`; host ports PG:5432, Redis:6379, API:8000, Caddy:8080 (http); `web` one-shot builds SPA into `web_dist`. |
| **Dev (no Docker)** | `dev_services.ps1 start` + `uvicorn --reload` | Portable Postgres:5433 + Redis:6380 from `%LOCALAPPDATA%\mh-dev`; frontend via `npm run dev` (:5173, proxy `/api`→:8000). |
| **Prod** | `-f docker-compose.yml -f docker-compose.prod.yml up -d` | Caddy TLS (Caddyfile.prod, HSTS/auto-cert), real `JWT_SECRET` required, no host port exposure, `JOB_MODE=queue`, workers scalable. |

**Network boundaries.** Only Caddy is internet-facing in prod; API/worker/PG/Redis sit on the internal
compose network. **Storage:** named volumes `pg_data`, `redis_data`, `uploads` (shared api↔worker),
`engine_cache`, `hf_cache`, `corpus_data`, `schema_versions`, `schema_aliases`, `web_dist`.
**Secrets:** `.env` (git-ignored); boot-time validation rejects the placeholder JWT secret.
**Load balancing / gateways:** Caddy is the single gateway; horizontal scale is at the worker tier
(stateless, Redis-decoupled) and can extend to multiple API replicas behind Caddy.

---

## 5. Architecture Review

### Strengths (evidence-backed)
- **Engine-adapter boundary (ADR-0001)** enforced by CI — decouples ML churn, enables a mock engine
  for fast/hermetic tests and demos.
- **Strict layering** enforced by review + `check_engine_boundary.py` keeps SQL, business logic, and
  HTTP concerns separate.
- **Reproducibility by construction** — two-axis version pin (schema version + ontology snapshot)
  stamped on every study.
- **Operational safety** — fail-open rate-limit/idempotency, backpressure (503 + Retry-After), engine
  work off the event loop, arq retries + hard timeout, ontology dictionary fallback.
- **Security depth** — boot-time secret validation, RBAC, lockout, HIBP, CSP/security headers,
  append-only audit, optimistic concurrency.

### Risks & bottlenecks (prioritized)

| # | Risk | Type | Evidence | Recommendation |
|---|---|---|---|---|
| P1 | **Postgres & Redis are single-node SPOFs** | Reliability | compose has one `postgres`, one `redis` | Managed HA Postgres + Redis (or Sentinel/cluster); document RPO/RTO + backups. |
| P2 | **KB bundle (~1.4 GB) seeded per env; not runtime-pulled** | Ops/Scale | `kb-import`, offline flags | Version + checksum the bundle (already sha-pinned); publish to object storage; automate seed in deploy. |
| P3 | **Engine cold start** (model load + NCI warm ~90 s) | Performance | `pre_warm()`, `_warm_nci_cache()` | Keep pre-warm; add readiness gating so cold workers don't take traffic; consider a warm pool. |
| P4 | **External vocab API coupling** (NCI/OLS/UMLS) | Reliability | KB db_clients, persisted NCI cache | Add explicit timeouts/circuit-breaker + cache TTL policy; the dictionary fallback already contains blast radius. |
| P5 | **Metrics are per-process; no central Prometheus/Grafana in-repo** | Observability | `/metrics` endpoint only | Add a Prometheus scrape + Grafana dashboards + alert rules (queue depth, job failure rate, p95). |
| P6 | **No distributed tracing** | Observability | request-id only | Add OpenTelemetry traces across API→worker→engine for end-to-end latency attribution. |
| P7 | **Single wheel pin can drift from tested engine** | Correctness | repo memory: wheel drift incident | Keep wheel-vs-source diff check in release; treat engine bumps as gated changes. |
| P8 | **Large uploads processed in one worker thread** | Performance | `_run_pipeline` reads full CSV | Enforce `MAX_UPLOAD_ROWS` on public instances; consider chunked/streamed parsing for very large tables. |

### Missing / thin observability
Central metrics store, dashboards, alerting, and tracing are not in the repo (only the `/metrics`
endpoint + Sentry). This is the highest-leverage gap for production operability (P5, P6).

---

## 6. Architecture Decision Records

The repo already curates ADRs under [docs/adr/](../adr); summarized here with two inferred additions.

### ADR-0001 — Engine Adapter Pattern *(documented)*
- **Context:** app code imported the engine via `src.*`; every upstream rename broke ~15 imports.
- **Decision:** depend on `EngineProtocol`; confine `import metaharmonizer` to one adapter file; select
  impl via `ENGINE_IMPL`; enforce with CI.
- **Consequences:** cheap engine upgrades; mock-based testing; a small translation tax in the adapter.
- **Alternatives:** vendoring a copy (rejected — drift); direct imports (rejected — coupling).

### ADR-0002 — System Architecture & Two-Layer Curation KB *(documented)*
- **Context:** need auditable, reproducible, team-scale curation with reusable decisions.
- **Decision:** layered FastAPI + Postgres/Redis + adapter; **learned_decisions** with personal→shared
  promotion; version/snapshot pins; active-learning review order.
- **Consequences:** reuse across studies; admin governance; extra promotion workflow.

### ADR-0003 — Inline↔Queue job execution *(inferred; evidence: `JOB_MODE`, `tasks.py`, `arq_worker.py`)*
- **Context:** harmonization is CPU-heavy and slow; dev must stay one-process, prod must scale.
- **Decision:** one shared task run inline (thread) or via arq/Redis by `JOB_MODE`; retries + hard
  timeout + backpressure; progress on a Redis bus for process-agnostic live updates.
- **Consequences:** laptop-to-cluster with one env var; Redis becomes a key dependency.
- **Alternatives:** always-async (heavier dev), Celery (heavier than arq for this scope).

### ADR-0004 — Caddy single-gateway + offline models *(inferred; evidence: Caddyfile, compose offline flags)*
- **Context:** serve SPA + API same-origin, harden headers, avoid runtime model downloads.
- **Decision:** Caddy fronts SPA + `/api` + WS with CSP; models load offline from seeded caches
  (`HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`).
- **Consequences:** simple same-origin security + deterministic, network-independent model loads;
  requires a bundle-seeding step.

---

The sections above summarise decisions as reconstructed from source. The
maintained decision records are [ADR 0001](../adr/0001-engine-adapter-pattern.md),
[ADR 0002](../adr/0002-system-architecture.md),
[ADR 0003](../adr/0003-two-layer-curation-kb.md), and
[ADR 0004](../adr/0004-locked-decision-review.md), which reviews which of the
originally locked decisions still hold.

## 7. Diagram assets

| File | Tool | Renders |
|---|---|---|
| [architecture-overview.svg](../architecture-overview.svg) | SVG | Rendered system overview used in the README |
| [system-overview.svg](system-overview.svg) | SVG | Detailed component and stack map |
| [workspace.dsl](workspace.dsl) | Structurizr DSL | C4 Context / Container / Component / Deployment |
| [architecture.d2](architecture.d2) | [D2](https://d2lang.com) | Full system diagram (clusters, flows, CI, monitoring) |
| [architecture.drawio](architecture.drawio) | draw.io / diagrams.net | Editable, slide-ready diagram |
| engine & dashboard `*.md` | Mermaid | Inline in the two system-design docs |

**Render tips:** Mermaid renders in GitHub and VS Code (Markdown preview). D2: `d2 architecture.d2
architecture.svg`. Structurizr: paste into [structurizr.com/dsl](https://structurizr.com/dsl) or run
Structurizr Lite. draw.io: open directly in [app.diagrams.net](https://app.diagrams.net).
