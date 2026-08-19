# ADR 0004 — Review of the locked architecture decisions

**Status:** Accepted · **Date:** 2026-08-19
**Reviewers:** project maintainer · **Reviews:** [0002-system-architecture.md](0002-system-architecture.md)

ADR 0002 closed a list of options so that build work could proceed without
re-litigating them. Those decisions were taken before the system was deployed,
measured, or prepared for institutional handover. This ADR re-examines each one
against production evidence and states, for every decision, whether it still
holds and exactly what would reopen it.

The distinction that matters is between a decision that is **correct on the
merits** and one that was only correct **for a solo-maintained deployment**. The
second kind must not be inherited silently by whoever operates this next.

## 1. Verdicts

| Locked decision | Verdict | Basis |
|---|---|---|
| No microservices | **Holds** | The measured bottleneck is CPU inside one workload, not service coupling. Internal boundaries are CI-enforced. |
| No Kafka or event bus | **Holds** | Throughput is ~2,700 jobs/day/worker. Redis and arq already give bounded, observable, retryable delivery. |
| No live multi-master federation | **Holds** | Signed bundles with explicit human import is the correct trust model between institutions. |
| No always-on GPU or self-hosted LLM | **Holds** | CPU embeddings meet the warm 60-second objective; the ARM64 host has no GPU; the LLM stage is optional. |
| No live KB build on the VM | **Holds, now enforced** | The KB is built quarterly in CI, checksummed, accuracy-gated, and rolled out with automatic rollback. |
| No multi-tenancy | **Holds, scope clarified** | Isolation is per deployment. Per-user ownership scoping is not tenancy and must not be described as such. |
| No Kubernetes | **Relaxed** | Correct for this deployment, wrong as a permanent product rule. |
| No SSO | **Relaxed** | Defensible for a public demonstrator, not for institutional identity management. |
| No managed database | **Superseded for institutional deployment** | This is the weakest decision in ADR 0002 and the largest availability risk. |

## 2. Decisions that still hold

**No microservices.** Splitting services would multiply deployment, failure, and
observability surface without addressing the measured constraint, which is CPU
contention inside model execution. The engine adapter already provides the seam
for extracting the heavy component if that ever becomes necessary, so this
decision is reversible where it counts.

**No Kafka or event bus.** A durable partitioned log solves multi-consumer
replay and very high fan-out. Neither exists here. Redis with arq already
provides bounded queue depth, retries, dead-letter capture, and progress
publication. Reopen only if durable multi-consumer streaming becomes a
requirement, for example a cross-institution event feed.

**No live multi-master federation.** Mapping exchange uses signed bundles that a
curator explicitly imports and reviews. Live multi-master replication would
require conflict resolution, mutual trust infrastructure, and shared identity
across institutions, and it would weaken the guarantee that a human approved
every decision in the local knowledge base.

**No always-on GPU or self-hosted LLM.** Embedding inference on CPU meets the
measured warm objective. The current host is ARM64 without GPU, so this would
also force a multi-architecture image, a revalidated engine wheel, and new
accuracy and performance baselines. Reopen if queue wait becomes dominated by
embedding compute, or if an operator policy forbids external LLM calls — in
which case the answer is a small self-hosted model, not a permanently allocated
GPU.

**No live KB build on the VM.** Building on the production host would be slow,
subject to upstream rate limits, and unreviewable. The current pipeline is
strictly better: quarterly CI build, superset verification, before-and-after
accuracy gate, checksummed release, then a host-side rollout that probes the new
knowledge base and restores the previous volumes automatically on failure.

**No multi-tenancy.** The isolation boundary is the deployment. Study ownership
is enforced per user, but that is authorization, not tenancy: there is no tenant
identifier, no per-tenant configuration, and no administrative separation.
Serving a second institution from shared infrastructure is a schema and
authorization project, not a configuration change.

## 3. Decisions that change

### 3.1 Kubernetes — relaxed

ADR 0002 recorded "Kubernetes — absurd for one VM". That reasoning is sound for
this deployment and wrong as a permanent rule, because the receiving institution
may already standardise on an orchestrator.

The correct position: **Docker Compose is the reference deployment, not a
runtime dependency.** The application ships as ordinary OCI containers that read
configuration from the environment, hold no orchestrator-specific assumptions,
and keep state in PostgreSQL, Redis, and volumes. An operator may run those
images under any orchestrator.

What remains refused is the project maintaining a bespoke Kubernetes
distribution — charts, operators, and manifests — as part of this deliverable.
That is platform work owned by whoever runs the platform.

Two constraints must survive any orchestrator migration: the API and worker must
continue to share study object storage, which currently requires migrating
uploads to S3-compatible storage; and database migrations must run as a single
ordered step, never concurrently in every replica.

### 3.2 Single sign-on — relaxed

Email and password with JWT sessions, domain allow-listing, and admin approval
is proportionate for a public demonstrator. It is not proportionate for
institutional use, where identity, group membership, multi-factor policy, and —
most importantly — **offboarding** are managed centrally. A local password
database means a departing member keeps access until an administrator
remembers to revoke it.

Position: OIDC becomes a requirement when the service is operated by an
institution for its own staff. The change is contained because session issuance
is already centralised in one auth layer and roles already exist; the work is an
identity provider integration and a role-mapping decision, not an application
redesign.

### 3.3 Managed database — superseded for institutional deployment

ADR 0002 recorded "no managed DB in v1", justified by cost. Reviewed against
production, this is the weakest of the locked decisions and the largest residual
risk in the system.

PostgreSQL runs as a single container on the same VM as the application. It is
a single point of failure for **availability** and, between backups, for
**data**. Encrypted off-host backups and a drilled clean restore bound the
damage — the recovery point is up to 24 hours and recovery requires an operator
— but no backup makes a single node highly available.

Position: for a public demonstrator operated on a best-effort basis, the current
arrangement is acceptable and is documented as such. For an institutional
deployment, managed or replicated PostgreSQL is the default, and this decision
should be treated as superseded rather than inherited.

Reopen immediately when any of these is true:

- an availability commitment stronger than best-effort is made to users;
- losing up to 24 hours of curation decisions is unacceptable;
- recovery must not depend on one named person being reachable;
- the host is shared with other institutional workloads.

## 4. Consequences

- ADR 0002 remains the record of what was decided and why at the time. It is not
  rewritten; this ADR governs where the two disagree.
- Three decisions are no longer presented to a future operator as settled: the
  orchestrator, the identity provider, and the database topology.
- No change is made to the running deployment by this review. The current
  single-host topology and its limits stay documented in
  [architecture.md](../architecture.md) and [scaling-plan.md](../scaling-plan.md).
