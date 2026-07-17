# MetaHarmonizer

**Automated harmonization of clinical metadata into standardized, ontology-annotated, cBioPortal-compatible schemas.**

MetaHarmonizer maps inconsistent clinical metadata to a curated standard using a multi-stage ML pipeline, and presents the results in an interactive dashboard where curators review, correct, and export them — keeping expert oversight in the loop.

> GSoC 2026 — [Automated Clinical Metadata Harmonization Dashboard](https://github.com/cBioPortal/GSoC/issues/136)

## Why

Clinical metadata across studies is heterogeneous: the same concept appears as `AGE`, `AGE_AT_DIAGNOSIS`, or `DIAGNOSIS_AGE`; sex as `male` / `M` / `1`; treatments under dozens of synonyms. Manual harmonization does not scale. MetaHarmonizer automates the mapping and surfaces only the decisions that need a human.

## How it works

Two mapping steps, each reviewable:

1. **Schema mapping** — raw column headers → curated standard fields.
2. **Ontology mapping** — cell values → ontology terms (NCIt, UBERON, …).

Both run through a four-stage cascade (exact dictionary → alias → semantic embedding → optional LLM), stopping at the first high-confidence match. Low-confidence and unmapped items are ordered risky-first for curator review.

## Architecture

```
React SPA ──REST/WS──> FastAPI ──> PostgreSQL + Redis
                          │
                          └─> engine_adapter (EngineProtocol)
                                 └─> metaharmonizer engine  |  mock (tests)
```

Only `backend/app/engine_adapter/` may import the upstream `metaharmonizer` package — the ML engine sits behind a single, swappable seam (`ENGINE_IMPL=metaharmonizer|mock`).

## Tech stack

- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS, TanStack Query
- **Backend:** FastAPI, Pydantic v2, SQLAlchemy (async), Alembic
- **Data:** PostgreSQL 16, Redis 7 (jobs via arq, rate limiting, WebSockets)
- **Auth:** JWT access/refresh, Argon2id, RBAC, email verification
- **Engine:** `metaharmonizer` (SapBERT/MiniLM embeddings, NCI EVS, optional Gemini)

## Quick start

**Docker is the one supported path**, identical on Windows, macOS, and Linux. No config editing — `.env.example` is preconfigured with a dev login secret and the public knowledge-base download URL.

> Prerequisites: Docker Desktop (or Docker Engine + Compose), ~15 GB free disk, ~8 GB RAM.

```bash
git clone https://github.com/AhmedOsamaAli/metaHarmonizer.git
cd metaHarmonizer
cp .env.example .env                             # Windows PowerShell:  copy .env.example .env
docker compose --profile kb run --rm kb-import   # one-time: download + install the KB & models (~1.4 GB)
docker compose up --build                        # SPA + API + worker + Postgres + Redis behind Caddy
```

Open **http://localhost:8080** and register — the **first** account becomes the admin; later accounts are curators.

Skip-login, the optional Stage-4 LLM, native dev setup, and troubleshooting are all in **[SETUP.md](SETUP.md)**. Interactive API reference (OpenAPI/Swagger): `http://localhost:8000/docs`.

## Configuration

`.env.example` is the annotated catalogue. Key variables:

| Variable                | Required | Description                                     |
| ----------------------- | :------: | ----------------------------------------------- |
| `JWT_SECRET`            |   yes    | Signs tokens (boot fails if < 32 bytes).        |
| `DATABASE_URL`          |   yes    | `postgresql+asyncpg://…` DSN.                   |
| `REDIS_URL`             |   yes    | Jobs, rate limits, WS tickets.                  |
| `ALLOWED_EMAIL_DOMAINS` |   yes    | Signup allow-list; empty = registration closed. |
| `ENGINE_IMPL`           |          | `metaharmonizer` (default) or `mock`.           |
| `GEMINI_API_KEY`        |          | Enables the optional Stage-4 LLM rematch.       |

Migrations are managed by Alembic and are not auto-applied — run `alembic upgrade head` after schema changes.

## Testing

```bash
cd backend && pytest        # runs against Postgres + Redis
cd frontend && npm test     # Vitest
```

CI (GitHub Actions) runs the backend suite against ephemeral Postgres/Redis, the frontend build + tests, and the engine-boundary check on every push.

## Acknowledgments

- [MetaHarmonizer engine](https://github.com/shbrief/MetaHarmonizer) — the ML harmonization pipeline
- [cBioPortal](https://www.cbioportal.org/) — target schema for cancer genomics
- [NCI Thesaurus](https://ncithesaurus.nci.nih.gov/) — biomedical ontology
