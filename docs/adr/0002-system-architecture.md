# ADR 0002 — System architecture: modular monolith, single VM, decided infrastructure

**Status:** Accepted · **Date:** 2026-06-17
**Context owners:** app team (GSoC) · **Supersedes:** none · **Related:** [0001-engine-adapter-pattern.md](0001-engine-adapter-pattern.md)

> This ADR locks the structural decisions so building can proceed without re-litigating them:
> monolith vs microservices, datastore, queue, object storage, realtime transport, deploy model.
> This is the one-page decision record.

> **As built.** The structural decisions below still hold. Two infrastructure
> choices changed during delivery: the public instance runs Docker Compose on an
> Oracle Cloud VM rather than Kamal on Hetzner, and study objects stay on a host
> volume while Cloudflare R2 holds encrypted database backups. See
> [architecture.md](../architecture.md) for the current system.

---

## 1. Decision summary

| Concern | Decision | Not chosen (and why) |
|---|---|---|
| **App shape** | **Modular monolith** — one FastAPI app + in-process `arq` workers | Microservices / event-bus — needless ops + cost for a solo-maintained, single-tenant app |
| **Language/runtime** | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x | — |
| **Datastore** | **PostgreSQL** (container on the same VM) | Managed DB (extra cost); NoSQL (we need relational audit + versioning + FKs) |
| **Cache / queue / bus** | **Redis** — `arq` job queue, pub/sub for WebSocket, rate-limit, idempotency cache, WS tickets | Kafka/RabbitMQ — overkill at our volume |
| **Background jobs** | **`arq`** workers, in-process engine, one job per worker process | Celery (heavier); threads (CPU-bound inference needs process isolation) |
| **Object storage** | **S3-compatible object store** (Cloudflare R2) or **local disk**, selected by configuration | AWS S3 (egress fees on KB restore) |
| **Realtime** | **WebSocket** (`/ws/jobs/{study}`, `/ws/notify/{user}`) bridged via Redis pub/sub | SSE — no bidirectional headroom for future presence/lock features |
| **Reverse proxy / TLS** | **Caddy** (auto Let's Encrypt + HSTS) | nginx + manual certbot |
| **Frontend** | **React + Vite + TypeScript SPA**, `@tanstack/react-query` (server state) + Tailwind | Next.js/SSR — no SEO/SSR need for an authed tool |
| **ML engine** | Pinned upstream `metaharmonizer` **wheel** behind `engine_adapter/` (ADR 0001); KB pinned as a **bundle** = `(engine_sha, model_registry, kb_snapshot)` | Vendoring source; tracking `main` |
| **KB / FAISS** | **Pre-built offline → checksummed bundle → verified rollout**. Never built on the VM | Live KB build on the 2-vCPU VM (slow, EVS-rate-limited, fragile) |
| **Deploy** | **Docker Compose** on a single cloud VM, image rebuild + verified one-command rollback | Kubernetes — absurd for one VM; PaaS — cold starts |
| **Auth** | Email/password + JWT (access in-memory, refresh httpOnly cookie); domain allow-list signup; multiple admins | SSO/SAML/OIDC (out of v1) |
| **Tenancy** | **Single-tenant** per deployment; self-host = isolation boundary | Multi-tenancy — ~3–4 wks + a tax on every future feature |

## 2. The one picture

```
[ React SPA ]
     │ HTTPS + WS
     ▼
[ Caddy (TLS) ] → [ FastAPI app ] → [ Postgres (container) ]
                       │               [ Redis (container)  ]
                       │ enqueue            │ pub/sub → WS
                       ▼                    ▼
                 [ arq workers ] ── in-process ── [ engine_adapter / EngineProtocol ]
                       │                                   │
                       ▼                                   ▼
              [ object store / disk ]                 [ metaharmonizer wheel ]
              uploads · exports · KB bundle           │
                                                        ▼
                                          [ ~/.metaharmonizer/ FAISS+KB ]
                                          seeded from the published bundle
```

Self-host swaps the object store for local disk; everything else identical. One `docker-compose.yml` covers hosted + self-host.

## 3. Why monolith, not microservices (the headline call)

- **One maintainer** through the maintained-instance window. Microservices multiply deploy, observability, and failure surface — the opposite of what a solo operator can run.
- **Cost ceiling ≤ €10/mo** on a single small VM. Microservices imply multiple services/DBs/network hops that don't fit.
- **Self-host promise** is `docker compose up` in <30 min. A service mesh breaks that.
- **The "two logical services" in the grant** (harmonization engine + federation KB) are *logical*, not deployment units — they live behind one HTTP app via the engine adapter and the federation endpoints.
- **Modularity is preserved in-process:** clear module boundaries (`routers / services / repositories / workers / engine_adapter`) + the CI-enforced engine boundary give the separation benefits without the distributed-systems cost. If a piece ever must scale out (e.g. a remote engine), the adapter is already the seam.

## 4. Locked "no"s (so they don't get reopened)

No microservices · no Kubernetes · no Kafka/event bus · no multi-tenancy · no managed DB in v1 · no SSO in v1 · no live multi-master federation · no always-on GPU/self-hosted LLM · no live KB build on the VM.

> **Reviewed.** [ADR 0004](0004-locked-decision-review.md) re-examines this list
> against production evidence. Six still hold; Kubernetes and SSO are relaxed,
> and the managed-database decision is superseded for institutional deployment.
> Where the two disagree, ADR 0004 governs.

## 5. Consequences

- **Positive:** cheap, simple to operate solo, trivial self-host, fast local dev (one compose), clean handover to cBioPortal infra (the same Compose definition).
- **Negative / accepted:** single-VM is not multi-AZ HA (mitigated by nightly encrypted backups + a drilled restore); vertical scaling only — fine for the target service objectives; one big process means a bad deploy affects everything (mitigated by verified rollback + graceful degradation per dependency).
