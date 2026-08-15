# Capacity and ML expansion plan

## Current boundary

| Surface | Supported planning limit | Measured constraint |
|---|---:|---|
| Active dashboard curators | 50 | API/host CPU; throughput plateaus near 100 requests/second |
| Real ML concurrency | 2 jobs per worker | CPU contention; four jobs improved throughput little and increased latency |
| Representative ML throughput | 2,700 jobs/day/worker | 50% headroom applied to the measured 31.60-second workload |
| Queue | warning 160, reject 200 | Configured Redis backpressure |
| Upload | 50 MiB/study, 3 active jobs/user | Configured safety limits |

The dashboard and ML limits are separate. Fifty active reviewers does not mean
fifty simultaneous model executions.

“Active” means the controlled k6 workload or, in production reporting, distinct
authenticated users seen in a rolling five-minute window. Total registered
accounts are not a concurrency metric and currently have no benchmarked maximum.

## Expansion triggers

Expansion starts only when retained production evidence shows one of these for
at least three business days, or a scheduled event requires it:

- p95 dashboard latency above 800 ms at normal peak traffic;
- more than 40 simultaneously active curators;
- queue depth above 40 for 15 minutes or oldest-job wait above five minutes;
- worker CPU saturation while queued work exists;
- forecast less than 30 days to the 70% disk threshold.

The 800 ms trigger is 80% of the one-second p95 objective, leaving time to act
before users experience an SLO breach.

In production, use the five-minute distinct-active-user count as an early-warning
proxy. It is intentionally conservative and is not mathematically identical to
simultaneous k6 VUs. Confirm a scale decision with request rate, latency, CPU,
queue, and job evidence rather than this count alone.

## Phase 0: owner and billing decision

Before changing OCI resources:

1. Confirm tenancy type, current charges/credits, service limits, and available
   A1 capacity in Ashburn.
2. Record whether 4 OCPU/24 GB is billed or covered by account-specific terms.
   Current public Always Free documentation lists 2 A1 OCPUs/12 GB total.
3. Select and price no-change, 6 OCPU/24 GB, and 8 OCPU/24 GB options.
4. Complete the off-host backup/restore drill before any shape change.

Changing an OCI shape reboots the VM. Regional A1 capacity is not guaranteed,
and a failed capacity allocation can leave the original shape unchanged.

## Phase 1: vertical API capacity

CPU, not memory, was the dashboard bottleneck. If expansion is approved, resize
to 6 OCPUs while retaining 24 GB memory; use 8 only if 6 is unavailable or the
repeat benchmark still lacks headroom.

Extra OCPUs alone may not help a single Uvicorn process. Test two API processes
or replicas behind Caddy, then repeat the distinct-user ladder. Before enabling
multiple API processes:

- cap aggregate SQLAlchemy pools below PostgreSQL `max_connections`;
- prove WebSocket and Redis-backed notification behavior across replicas;
- run migrations as a one-shot step rather than concurrently in every replica;
- measure memory because any API path that loads the engine can duplicate model
  state per process;
- verify Caddy load balancing and health removal under container failure.

Acceptance: 50 users meet p95 <=1 second and p99 <=2 seconds with at least 25%
p95 headroom, zero fixture errors, healthy production-shaped dependencies, and
a successful replica-failure test.

## Phase 2: same-host ML tuning

Do not raise `WORKER_MAX_JOBS` above two or add same-host worker containers merely
because memory is free. The current workload is CPU-bound; another container
duplicates model state and competes for the same cores.

After a CPU resize, rerun real-engine concurrency at 1, 2, 3, and 4 jobs. Raise
the worker setting only if throughput scales, per-job p95 remains within the
warm 60-second objective, host memory retains 4 GiB reserve, and API SLOs still
pass under mixed read/ML load.

## Phase 3: remote ML workers

Remote workers are the preferred path when queue wait, rather than dashboard
traffic, drives expansion. The application already has an S3-compatible storage
backend, but production currently uses a local uploads volume. Complete these
prerequisites first:

1. Move study objects to S3/R2 and verify upload, rerun, export, retention, and
   deletion behavior. A remote worker cannot mount the current host-local volume.
2. Give workers private, authenticated access to central Redis and PostgreSQL;
   never expose either database publicly.
3. Seed and verify the same 1.6 GiB KB/model release on every worker node and pin
   the same application image and KB SHA.
4. Size each worker for measured model memory and two jobs; monitor queue age,
   job duration, RSS, retries, and dead letters.
5. Recalculate database pool totals and Redis connection limits across all
   API/worker processes.
6. Test worker loss, retry ownership, duplicate prevention, object availability,
   and version-stamped output before accepting traffic.

Same-host `docker compose --scale worker=N` does not create cross-host capacity.
A second VM needs its own worker-only deployment and operational lifecycle.

## Phase 4: service resilience

Capacity expansion does not create high availability. PostgreSQL, Redis, Caddy,
and the single OCI VM remain failure domains. Institution-grade resilience would
also require an external load balancer, multiple API hosts, durable object
storage, managed or replicated PostgreSQL/Redis, external uptime checks, tested
failover, and named operators.

## Engine and platform limitations

- Current OCI A1 is ARM64 and has no GPU. Moving to x86 or GPU requires rebuilding
  and scanning multi-architecture images, validating the vendored engine wheel,
  selecting compatible PyTorch packages, and rerunning accuracy/performance tests.
- GPU acceleration is not established for the end-to-end engine. Do not buy a
  GPU shape until profiling proves embedding/model inference dominates and a
  representative CUDA benchmark shows useful cost-adjusted throughput.
- Each worker process prewarms its own engine; additional processes duplicate
  model memory.
- FAISS/SQLite KB assets are read-only at runtime but must be distributed and
  version-verified per node.
- Queue depth is bounded at 200, job timeout is 15 minutes, and retries are
  bounded. Scaling workers does not remove those product safeguards.
- The 50 GB boot disk can be expanded online but not shrunk; the guest partition
  and filesystem must then be extended. Current pressure is mostly reclaimable
  Docker build cache, so expansion is not yet justified.
- There is no autoscaler. Every scale change currently needs an operator,
  benchmark, rollback plan, and updated cost/ownership record.

## Decision evidence

Every expansion changes the published capacity only after:

- before/after cost and OCI shape evidence;
- the distinct-user ladder and mixed read/real-ML test;
- resource and queue-age reports;
- failure/rollback drills;
- updated service objectives and operations runbook;
- protected CI/security checks and an exact-revision deployment record.