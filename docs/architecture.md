# Architecture

## System context

MetaHarmonizer is a human-in-the-loop metadata harmonization system. Curators
upload de-identified tabular metadata, review schema and ontology proposals,
approve corrections, inspect quality, and export standardized datasets.

```mermaid
flowchart LR
    Curator[Curator browser] -->|HTTPS| Edge[Caddy]
    Edge -->|Static assets| SPA[React application]
    Edge -->|REST and WebSocket| API[FastAPI API]
    API --> DB[(PostgreSQL)]
    API --> Queue[(Redis / arq)]
    Queue --> Worker[ML worker]
    Worker --> DB
    Worker --> Objects[Study objects]
    Worker --> Models[Versioned KB and model cache]
    API --> Objects
    Ops[Systemd operations] --> API
    Ops --> Backup[Encrypted R2 backups]
```

## Trust boundaries

| Boundary | Data crossing it | Controls |
|---|---|---|
| Browser to edge | Credentials, metadata, decisions, exports | TLS, JWT/refresh sessions, RBAC, CSP, rate limits |
| API to PostgreSQL | Users, studies, mappings, audit and job state | Private Compose network, credentials, migrations, ownership filters |
| API/worker to Redis | Queue jobs, progress, rate-limit and activity state | Private Compose network, bounded queue, expirations |
| API/worker to object storage | Uploaded metadata and generated artifacts | Owner-scoped keys, retention, local volume or private S3-compatible backend |
| Runtime to upstream providers | Email, optional LLM, KB build sources | Host-only secrets, explicit optional configuration, offline runtime models |
| Host to backup storage | Encrypted PostgreSQL dump | AES-256-GCM before upload, bucket-scoped credentials, restore drills |

The public deployment currently uses a local persistent volume for study
objects. R2 is dedicated to encrypted PostgreSQL backups. Moving workers to a
second host requires migrating study objects to the existing S3-compatible
storage adapter first.

## Backend ownership

The backend follows explicit dependency direction:

```mermaid
flowchart LR
    Routers --> Services
    Routers --> Repositories
    Services --> Repositories
    Services --> Adapter[Engine adapter]
    Repositories --> Models[SQLAlchemy models]
    Adapter --> Engine[Vendored MetaHarmonizer engine]
```

- **Routers** own HTTP/WebSocket transport, authentication dependencies, and
  response contracts.
- **Services** own reusable workflows and domain orchestration.
- **Repositories** are the persistence boundary.
- **Engine adapter** is the only application package allowed to import the
  upstream `metaharmonizer` package. CI enforces this rule.
- **Workers** execute bounded asynchronous tasks and publish progress through
  Redis; durable status remains in PostgreSQL.

Some routers still contain transaction orchestration. This is accepted where
the workflow is short and transport-specific, but new reusable behavior should
move into services rather than expanding router modules further.

## Frontend ownership

- `src/api/` owns typed HTTP calls and response shapes.
- `src/hooks/` owns shared server-state queries and invalidation.
- `src/context/` owns authentication, jobs, notifications, and theme state.
- `src/pages/` composes workflows.
- `src/components/` and `src/components/ui/` own reusable product and visual
  components.

TanStack Query owns server state. Pages should not duplicate remote data in
local state unless editing requires a temporary draft. Global rendering errors
are contained by the application error boundary; page-level API failures must
remain visible and retryable.

## Data and consistency

- PostgreSQL is the source of truth for users, studies, mapping decisions,
  schema versions, ontology snapshots, jobs, and audit history.
- Redis data is operational and reconstructable; it is not the source of truth
  for completed work.
- Study ownership is enforced for reads, mutations, exports, reruns, and
  progress access.
- Schema and ontology versions are stamped onto studies for reproducibility.
- Learned decisions are layered: personal decisions override shared decisions.
- Alembic is the only supported schema-change mechanism.

## Runtime and deployment

The production topology is a single OCI host running Docker Compose. API and
worker share one application image but use different commands. Caddy terminates
TLS and serves the built SPA. One-shot services publish frontend assets, seed
the KB, run backups, and perform operational checks.

This is intentionally portable but not highly available. PostgreSQL, Redis,
Caddy, and the host are single failure domains. The phased path to API replicas,
remote workers, object storage, and replicated state is documented in
[scaling-plan.md](scaling-plan.md).

## Architecture invariants

Changes must preserve these rules:

1. No direct upstream-engine imports outside the adapter.
2. No production data or secrets in source control, logs, tests, or public issues.
3. Every study-scoped operation enforces ownership.
4. Long-running work is queued, bounded, retryable, observable, and idempotent.
5. PostgreSQL changes use migrations with compatibility and rollback analysis.
6. KB/model updates are versioned, integrity checked, benchmarked, and reversible.
7. Operational changes include health verification and a rollback path.

## Known limitations and delegated work

- The deployment is single-host and has no automatic failover.
- Production metrics are retained locally; durable external metrics history is
  delegated to a later institutional deployment.
- Remote ML workers require private database/Redis connectivity and S3-compatible
  study-object storage.
- API and worker CPU remain the measured scaling constraint; adding concurrency
  without benchmarks is unsupported.
- Large page modules may be decomposed when feature work resumes, but module
  size alone does not justify a release-risk refactor.# Architecture

## System context

MetaHarmonizer is a human-in-the-loop metadata harmonization service. Curators
upload de-identified study metadata, review schema and ontology candidates, and
export standardized data. The matching engine proposes; curators remain the
source of final decisions.

```mermaid
flowchart LR
    Curator[Curator browser]
    Agent[AI client / MCP host]
    Portal[cBioPortal or downstream tools]

    subgraph Host[MetaHarmonizer deployment boundary]
        Caddy[Caddy: TLS and routing]
        SPA[React SPA]
        API[FastAPI API]
        Redis[(Redis: queue, rate limits, pub/sub)]
        Worker[arq ML worker]
        DB[(PostgreSQL)]
        Files[(Uploads / object storage)]
        Adapter[Engine adapter]
        Engine[MetaHarmonizer engine]
        KB[(Versioned KB and model cache)]
    end

    Curator -->|HTTPS| Caddy
    Caddy --> SPA
    Caddy -->|REST / WebSocket| API
    API --> DB
    API --> Redis
    API --> Files
    Redis --> Worker
    Worker --> DB
    Worker --> Files
    Worker --> Adapter --> Engine --> KB
    Agent -->|MCP, optional| Adapter
    API -->|validated exports| Portal
```

Production currently uses one host. PostgreSQL, Redis, Caddy, API, and worker
therefore share a failure domain; horizontal scaling does not by itself create
high availability.

## Application layers

```mermaid
flowchart TB
    Routes[FastAPI routers]
    Services[Application services]
    Repositories[Repositories]
    Database[(SQLAlchemy / PostgreSQL)]
    Queue[Queue and worker tasks]
    Protocol[EngineProtocol]
    Adapter[MetaHarmonizer adapter]
    Upstream[Vendored upstream engine]

    Routes --> Services
    Routes --> Repositories
    Services --> Repositories --> Database
    Routes --> Queue --> Services
    Services --> Protocol
    Protocol --> Adapter --> Upstream
```

- Routers own HTTP contracts, authentication, authorization, and response codes.
- Services own workflows and domain transformations.
- Repositories own persistence queries and transactions.
- Worker tasks own asynchronous execution, retries, and progress publication.
- `backend/app/engine_adapter/` is the only application package allowed to import
  the upstream engine. CI enforces this dependency boundary.

Some simple routes call repositories directly. This is intentional where there
is no reusable domain workflow; shared behavior belongs in services.

## Harmonization lifecycle

```mermaid
stateDiagram-v2
    [*] --> queued: validated upload
    queued --> running: worker starts
    running --> review: candidates persisted
    running --> queued: bounded retry
    running --> failed: retries exhausted
    queued --> cancelled
    running --> cancelled
    review --> completed: curator files study
    review --> [*]: export / continued curation
```

Each study records the schema version and ontology snapshot used to produce its
mappings. Curator decisions are stored separately from the versioned engine KB:
personal decisions override shared decisions, and administrators can promote or
stop sharing decisions without rewriting study history.

## Persistent state

| State | Owner | Notes |
|---|---|---|
| Users, studies, mappings, versions, audit | PostgreSQL | Alembic-managed relational source of truth |
| Queue, rate limits, progress, active-user window | Redis | Recoverable operational state; job rows remain in PostgreSQL |
| Uploaded source and exports | Local volume or S3-compatible storage | Remote workers require shared object storage |
| Engine KB and model cache | Versioned read-only volumes | Bundle SHA is recorded with ontology snapshots |
| TLS certificates | Caddy volume | Renewed automatically |
| Encrypted backups | Dedicated S3/R2 bucket | Host-side AES-256-GCM encryption |

## Security boundaries

- Caddy is the only public network entry point.
- PostgreSQL and Redis are not exposed on host ports in production.
- API and worker run as non-root UID/GID 1000 with `no-new-privileges`.
- JWT sessions and personal API tokens resolve to role-based authorization.
- Uploads are owner-scoped; administrators have operational host/database access
  and must be governed as data operators.
- Prometheus metrics require an admin-scoped token.
- Secrets and encryption keys are host-only and excluded from Git.

## Operations

Systemd adapters run encrypted backups, KB updates, five-minute health checks,
and daily capacity reports. GitHub Actions enforce tests, coverage, dependency
audits, secret scanning, CodeQL, container scans, SBOM generation, non-root
runtime checks, and engine-boundary contracts.

See [production operations](production-operations.md), [service objectives](service-level-objectives.md),
and [scaling](scaling-plan.md).

## Design principles and trade-offs

- **Human authority:** automation ranks and proposes; curator decisions remain explicit.
- **Dependency inversion:** the dashboard depends on `EngineProtocol`, not the
  upstream package.
- **Reproducibility:** schema versions, ontology snapshots, bundle hashes, and
  audit events are persisted.
- **Fail bounded:** queue depth, retries, job timeouts, upload size, rate limits,
  and per-user active jobs are capped.
- **Portable deployment:** behavior is defined through containers, environment
  variables, volumes, and one-shot commands.
- **Honest scaling:** API reads and ML jobs have separate measured limits.

## Known limitations and delegated work

These are deliberate follow-up items, not hidden guarantees:

1. Add external uptime monitoring and retained metrics history; host-local checks
   cannot report when the host itself is unreachable.
2. Move uploads to shared object storage before deploying remote workers.
3. Recalculate aggregate database pools before adding API/worker processes.
4. Add managed or replicated stateful services before claiming high availability.
5. Add mixed dashboard/real-ML load tests after any CPU or worker expansion.
6. Continue raising component-level frontend coverage and decomposing the largest
   review/admin pages as behavior changes require.
