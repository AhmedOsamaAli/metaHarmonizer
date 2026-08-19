# MetaHarmonizer — Dashboard Services System Design (High-Level)

> Presentation-ready architecture of the **curator dashboard platform**: the SPA,
> the reverse proxy, the FastAPI service layers, the job pipeline, the datastores,
> and the cross-cutting concerns. Claims are grounded in source with inline references.

---

## 1. System context

MetaHarmonizer Dashboard is a **curator-in-the-loop** web application: a curator uploads a study's
metadata table, the engine proposes column→field and value→ontology mappings with confidence, and the
curator reviews/edits before exporting **cBioPortal-compatible** outputs. Every decision is audited
and every study is pinned to a schema version + ontology snapshot for reproducibility.

```mermaid
flowchart TB
    Curator(["Curator / Admin<br/>(browser)"]):::person
    Agent(["LLM agent<br/>(Claude/Cursor)"]):::person

    subgraph MH["MetaHarmonizer platform"]
        SPA["React SPA"]:::app
        API["FastAPI API + Worker"]:::app
        MCP["MCP server"]:::app
    end

    Gemini["Gemini API"]:::ext
    Vocab["NCI EVS · OLS · UMLS"]:::ext
    Resend["Resend (email)"]:::ext
    HIBP["HaveIBeenPwned"]:::ext
    Sentry["Sentry"]:::ext
    cBio["cBioPortal (import target)"]:::ext

    Curator --> SPA --> API
    Agent --> MCP --> API
    API --> Gemini
    API --> Vocab
    API --> Resend
    API --> HIBP
    API --> Sentry
    API -->|"harmonized export"| cBio

    classDef person fill:#e0e7ff,stroke:#4338ca,color:#1e1b4b
    classDef app fill:#dbeafe,stroke:#1d4ed8,color:#0b2a5b
    classDef ext fill:#f1f5f9,stroke:#64748b,color:#1e293b
```

---

## 2. Container view (runtime processes)

```mermaid
flowchart TB
    Browser(["Browser SPA<br/>React 18 · Vite · TS · Tailwind<br/>React Query · Recharts"]):::app

    subgraph edge["Edge"]
        Caddy["Caddy reverse proxy<br/>:8080 (dev) / :443 (prod)<br/>SPA static + /api/* + WS<br/>CSP + security headers"]:::proxy
    end

    subgraph svc["Application (same image, two commands)"]
        API["FastAPI API :8000<br/>uvicorn<br/>routers → services → repositories"]:::app
        Worker["arq worker<br/>harmonize jobs + cron"]:::app
    end

    subgraph data["State"]
        PG[("PostgreSQL 16<br/>studies · mappings · audit · users…")]:::db
        Redis[("Redis 7<br/>queue · pub/sub · rate-limit · idempotency")]:::cache
        OBJ[["Object store<br/>uploads / exports<br/>file:// or S3/R2"]]:::store
        KB[["KB volumes<br/>FAISS · models · corpora"]]:::store
    end

    EA["engine_adapter → metaharmonizer"]:::eng

    Browser -->|HTTPS| Caddy
    Caddy -->|"/api/*, /healthz, /metrics, WS"| API
    Caddy -->|"static SPA (web_dist)"| Browser
    API -->|"enqueue (queue mode)"| Redis
    Redis -->|"dequeue"| Worker
    API <-->|"pub/sub progress"| Redis
    API --> PG
    Worker --> PG
    API --> OBJ
    Worker --> OBJ
    API --> EA
    Worker --> EA
    EA --> KB

    classDef app fill:#dbeafe,stroke:#1d4ed8,color:#0b2a5b
    classDef proxy fill:#fae8ff,stroke:#a21caf,color:#3b0764
    classDef db fill:#dcfce7,stroke:#15803d,color:#0b3d1e
    classDef cache fill:#fee2e2,stroke:#b91c1c,color:#450a0a
    classDef store fill:#fef9c3,stroke:#ca8a04,color:#5b4708
    classDef eng fill:#ede9fe,stroke:#6d28d9,color:#2e1065
```

Evidence: [docker-compose.yml](../../docker-compose.yml) (same `./backend` image for `api` and
`worker`, differing only by `command`), [Caddyfile](../../Caddyfile) routing,
[main.py](../../backend/app/main.py) router mounting.

---

## 3. The layered backend (enforced boundaries)

The backend follows a strict, **CI-enforced** dependency direction
([backend/STRUCTURE.md](../../backend/STRUCTURE.md)):

```mermaid
flowchart LR
    RT["routers/<br/>HTTP only — parse, validate,<br/>shape responses"]:::l1
    SV["services/<br/>business logic — no SQL,<br/>no engine import"]:::l2
    RP["repositories/<br/>all SQL / ORM"]:::l3
    DBm["db/ (SQLAlchemy async)"]:::l4
    EA["engine_adapter/<br/>(only engine importer)"]:::eng
    CORE["core/ (settings, logging, metrics,<br/>limits, jobs, storage, security)"]:::core

    RT --> SV --> RP --> DBm
    SV --> EA
    RT -.-> CORE
    SV -.-> CORE
    RP -.-> CORE

    classDef l1 fill:#dbeafe,stroke:#1d4ed8,color:#0b2a5b
    classDef l2 fill:#e0f2fe,stroke:#0369a1,color:#0b2a5b
    classDef l3 fill:#ccfbf1,stroke:#0f766e,color:#053b35
    classDef l4 fill:#dcfce7,stroke:#15803d,color:#0b3d1e
    classDef eng fill:#ede9fe,stroke:#6d28d9,color:#2e1065
    classDef core fill:#fef9c3,stroke:#ca8a04,color:#5b4708
```

**Rules (from STRUCTURE.md):** routers do no SQL and no engine calls; services hold business logic
with no raw SQL and no `metaharmonizer` import; repositories own all SQL; only services/workers call
the engine adapter; `core/` is depended on by everyone and depends on nothing app-specific.

### 3.1 API surface (v1)

Mounted in [main.py](../../backend/app/main.py); prefixes from each router file:

| Router | Prefix | Purpose |
|---|---|---|
| `auth` | `/api/v1/auth` | register, login, verify-email, forgot/reset-password, refresh, logout |
| `admin` | `/api/v1/admin` | users, roles, approvals, force-logout, **schema-versions**, aliases, learned-decision promotion |
| `tokens` | `/api/v1/tokens` | personal API tokens |
| `harmonize` | `/api/v1` | **POST /harmonize** (202), job status, target-schemas, schema-versions |
| `mappings` | `/api/v1/mappings` | list, **review-queue** (active-learning order), accept/reject/edit, batch |
| `ontology` | `/api/v1/ontology` | value-mapping review, term **search**, snapshots |
| `quality` | `/api/v1/quality` | per-study coverage / confidence / stage metrics |
| `export` | `/api/v1/export` | harmonized CSV, cBioPortal TSV, study ZIP, report JSON, labeled dataset |
| `federation` | `/api/v1/federation` | public-key, signed export, verified import (Ed25519) |
| `audit` | `/api/v1/audit` | append-only activity log query |
| `ws` | `/api/v1` | WS **ticket** + `/jobs/{study_id}` live progress |
| `health` | `/` | `/healthz`, `/readyz`, `/health/engine` |

### 3.2 Cross-cutting middleware (order from `main.py`)

`install_observability` (request-id + unified error envelope) → `SecurityHeadersMiddleware` →
`MetricsMiddleware` (Prometheus golden signals at admin-scoped `/metrics`) → `install_limits`
(sliding-window rate limit + idempotency, **fail-open** if Redis down) → CORS (explicit origins,
methods, headers; `Idempotency-Key` allowed).

---

## 4. Domain services & data model

**Services** ([backend/app/services/](../../backend/app/services)):
`harmonizer` (orchestration + dictionary ontology fallback), `exporter` (cBioPortal / harmonized /
report / labeled formats), `analytics` (quality metrics), `active_learning` (risky-first,
group-look-alikes review queue), `learned_apply` (reuse remembered decisions), `linkml_gate`
(schema validation), `mapping_evaluation`, `schema_diff`, `federation`.

**Core data model** ([backend/app/db/models.py](../../backend/app/db/models.py)):

```mermaid
erDiagram
    USERS ||--o{ STUDIES : owns
    STUDIES ||--o{ MAPPINGS : has
    STUDIES ||--o{ ONTOLOGY_MAPPINGS : has
    MAPPINGS ||--o{ MAPPING_VERSIONS : "append-only history"
    SCHEMA_VERSIONS ||--o{ STUDIES : "pins (schema_version_id)"
    ONTOLOGY_SNAPSHOTS ||--o{ STUDIES : "pins (ontology_snapshot_id)"
    USERS ||--o{ LEARNED_DECISIONS : "personal / shared"
    USERS ||--o{ SESSIONS : has
    USERS ||--o{ API_TOKENS : has
    STUDIES ||--o{ JOB_RUNS : tracks
    USERS ||--o{ AUDIT_EVENTS : actor

    STUDIES {
      string id PK
      string status
      bool exported
      int schema_version_id FK
      int ontology_snapshot_id FK
      int version "optimistic lock"
    }
    MAPPINGS {
      int id PK
      string raw_column
      string matched_field
      float confidence_score
      string stage
      string status
      string curator_field
    }
```

Key traits: **append-only audit** (`audit_events`) + **mapping version history** (`mapping_versions`);
**optimistic concurrency** (`OptimisticVersionMixin` → 409 on stale writes); **two-axis reproducibility
pin** (`schema_version_id` + `ontology_snapshot_id`); **two-layer curation KB**
(`learned_decisions`: personal vs admin-promoted shared — ADR-0002).

---

## 5. Workflow — request lifecycle (upload → review → export)

```mermaid
sequenceDiagram
    autonumber
    actor C as Curator (SPA)
    participant CA as Caddy
    participant API as FastAPI
    participant R as Redis
    participant WK as Worker/thread
    participant EA as EngineAdapter
    participant DB as Postgres

    C->>CA: POST /api/v1/harmonize (CSV, Idempotency-Key)
    CA->>API: proxy
    API->>API: authz + size/row guard + backpressure check
    alt queue depth ≥ JOB_MAX_QUEUE_DEPTH
        API-->>C: 503 + Retry-After
    else accepted
        API->>DB: create study + job_run (queued)
        alt JOB_MODE=queue
            API->>R: enqueue harmonize_job
            R->>WK: dequeue
        else JOB_MODE=inline
            API->>WK: run in background thread
        end
        API-->>C: 202 Accepted (job id)
    end

    C->>API: GET /api/v1/ws/ticket → WS /api/v1/jobs/{study}
    WK->>EA: harmonize_schema() then map_values()
    EA-->>WK: mappings + ontology mappings
    WK->>R: publish progress (parse→schema→ontology→done)
    R-->>C: live progress over WebSocket
    WK->>DB: persist mappings, stamp version pins, status=review

    C->>API: review-queue → accept / reject / edit (batch)
    API->>DB: update mapping (+ mapping_versions, audit_events)
    C->>API: GET /export/{study}/cbioportal
    API->>DB: read confirmed mappings
    API-->>C: cBioPortal TSV / ZIP / report / labeled CSV
```

**Resilience:** idempotency keys de-dupe retried uploads; backpressure returns `503 + Retry-After`
past `JOB_MAX_QUEUE_DEPTH`; rate limiting and idempotency **fail open** if Redis is unavailable;
engine work runs off the event loop; live progress is process-agnostic (any connected client sees it
via the Redis bus). Evidence: [core/settings.py](../../backend/app/core/settings.py),
[workers/tasks.py](../../backend/app/workers/tasks.py), [core/limits.py](../../backend/app/core/limits.py).

---

## 6. Workflow — authentication & authorization

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant API as FastAPI (auth)
    participant DB as Postgres
    participant M as Resend (email)
    participant H as HIBP

    U->>API: POST /register (email, password)
    API->>H: k-anonymity breach check (fail-open)
    API->>DB: create user (approved? by domain rule)
    API->>M: verification link (or log in dev)
    U->>API: POST /verify-email (token)
    U->>API: POST /login
    alt too many failures
        API-->>U: 423 locked (LOGIN_MAX_FAILURES / lockout window)
    else ok
        API-->>U: access JWT (15m) + refresh cookie (httpOnly, 30d, Secure in prod)
    end
    U->>API: request with Bearer access token
    API->>API: verify JWT + role (curator|admin)
    U->>API: POST /auth/refresh (cookie) → new access token
```

Modes: `AUTH_MODE=jwt` (default; JWT secret strength enforced at boot) or `AUTH_MODE=none`
(dev bypass returning a real dev-admin row). Admin approval gates untrusted-domain signups; WS auth
uses a one-time 30 s ticket. Evidence: [routers/auth.py](../../backend/app/routers/auth.py),
[core/settings.py](../../backend/app/core/settings.py).

---

## 7. Deployment topology

```mermaid
flowchart TB
    subgraph dev["Dev — docker compose up (base + override)"]
        direction TB
        dCaddy["Caddy :8080 (http)"]:::proxy
        dAPI["api :8000 (--reload, bind-mount)"]:::app
        dWorker["worker (arq or inline)"]:::app
        dPG[("Postgres :5432")]:::db
        dRedis[("Redis :6379")]:::cache
        dWeb["web (one-shot SPA build → web_dist)"]:::job
    end

    subgraph prod["Prod — -f docker-compose.yml -f docker-compose.prod.yml"]
        direction TB
        pCaddy["Caddy :443 TLS (Caddyfile.prod)<br/>HSTS + auto-cert"]:::proxy
        pAPI["api (JWT required, no host ports)"]:::app
        pWorker["worker ×N (JOB_MODE=queue, scale)"]:::app
        pPG[("Postgres 16")]:::db
        pRedis[("Redis 7 AOF")]:::cache
    end

    CI["GitHub Actions<br/>ci · engine-boundary · kb-refresh · deploy-smoke"]:::ci
    CI -->|"build/test gate"| prod

    classDef proxy fill:#fae8ff,stroke:#a21caf,color:#3b0764
    classDef app fill:#dbeafe,stroke:#1d4ed8,color:#0b2a5b
    classDef db fill:#dcfce7,stroke:#15803d,color:#0b3d1e
    classDef cache fill:#fee2e2,stroke:#b91c1c,color:#450a0a
    classDef job fill:#ede9fe,stroke:#6d28d9,color:#2e1065
    classDef ci fill:#fef9c3,stroke:#ca8a04,color:#5b4708
```

- **Networking:** only Caddy is public in prod; API/worker/DB/Redis are on the internal compose
  network. Uploads volume is shared api↔worker so queue mode reads the same file.
- **Secrets:** `.env` (git-ignored); prod requires a real `JWT_SECRET` (boot fails otherwise);
  `docker-compose.prod.yml` skips the dev override.
- **CI/CD:** [ci.yml](../../.github/workflows/ci.yml) (backend on PG+Redis with mock engine +
  frontend build), [engine-boundary.yml](../../.github/workflows/engine-boundary.yml),
  [kb-refresh.yml](../../.github/workflows/kb-refresh.yml),
  [deploy-smoke.yml](../../.github/workflows/deploy-smoke.yml); E2E via Playwright ([e2e/](../../e2e)).

---

## 8. Non-functional posture (for the review)

| Concern | How it's handled | Confidence |
|---|---|---|
| Scalability | Stateless API + horizontally-scaled arq workers (`--scale worker=N`); Redis-decoupled jobs. | High |
| Availability | Healthchecks + `depends_on: service_healthy`; fail-open limits; ontology dictionary fallback. | High |
| Consistency | Optimistic version locking (409); append-only audit + mapping versions. | High |
| Security | JWT + refresh cookie, RBAC, lockout, HIBP, CSP/security headers, rate-limit, upload guards. | High |
| Observability | Prometheus `/metrics`, structured logs + request-id, Sentry, `/healthz` `/readyz` `/health/engine`. | High |
| Reproducibility | Per-study schema-version + ontology-snapshot pins. | High |

---

*Companion documents:* [engine-system-design.md](engine-system-design.md) ·
[README.md](README.md) (full discovery, model, review, ADRs, exec summary) ·
C4 [workspace.dsl](workspace.dsl) · [architecture.d2](architecture.d2) · [architecture.drawio](architecture.drawio)
