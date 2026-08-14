# Production-shape multi-user and infrastructure assessment - 2026-08-15

## Scope and isolation

The test ran on the production Oracle host but not against production services,
data, accounts, networks, or volumes. A detached Git worktree and Compose project
`mh-capacity` created dedicated PostgreSQL, Redis, uploads, schema, and KB volumes
on port 18000. The engine was mocked so this test measured authenticated dashboard
and database concurrency; real ML throughput remains a separate limit.

Eighty distinct verified curator accounts were created only in the disposable
database. Each owned one review-ready 707-row, 141-column study. Every VU used its
own account/token and executed the dashboard fan-out: studies, target schemas,
review queue, quality metrics, and mappings. After the test, all isolated
containers, volumes, networks, worktree files, and secrets were removed.
Production `/healthz` returned 200 before, throughout, and after every rung.

SLOs:

- less than 1% failed HTTP requests;
- more than 99% checks;
- p95 below 800 ms;
- p99 below 2 seconds.

## Distinct active curators

Each rung ramped for 30 seconds, held for 45 seconds, and ramped down for 30
seconds with one second of think time.

| Active curators | Requests | Throughput | p95 | p99 | Failure rate | Checks | Result |
|---:|---:|---:|---:|---:|---:|---:|---|
| 10 | 3,595 | 34.0 req/s | 57 ms | enforced, not exported | 0% | 100% | pass |
| 20 | 7,065 | 65.8 req/s | 90 ms | enforced, not exported | 0% | 100% | pass |
| 30 | 9,265 | 86.5 req/s | 182 ms | enforced, not exported | 0% | 100% | pass |
| 40 | 10,120 | 93.7 req/s | 389 ms | enforced, not exported | 0% | 100% | pass |
| 50 | 10,595 | 97.5 req/s | 536 ms | enforced, not exported | 0% | 100% | pass |
| 60 | 10,850 | 98.1 req/s | 610 ms | 646 ms | 0% | 100% | pass |
| 70 | 11,095 | 100.8 req/s | 790 ms | 858 ms | 0% | 100% | edge: 10 ms p95 margin |
| 80 | 10,995 | 98.8 req/s | 945 ms | 991 ms | 0% | 100% | fail: p95 SLO |

Throughput flattened at approximately 98-101 requests/second from 50 users
onward. At 80 users throughput fell while latency rose, demonstrating CPU queueing
rather than useful scaling. The 80-user rung remained functionally correct but
is outside the response-time objective.

## Resource evidence

Live OCI metadata and host inspection:

| Resource | Current configuration |
|---|---|
| Shape | `VM.Standard.A1.Flex` |
| CPU | 4 OCPUs, Ampere Altra/Neoverse-N1 |
| Memory | 24 GB; approximately 20 GB available before testing |
| Network shape bandwidth | 4 Gbps |
| Root filesystem | 44.1 GiB usable; 67% used; approximately 15 GiB available |
| Swap | none |

At 60-70 users, host CPU idle reached 21% and the runnable queue reached 9. At
80 users, idle reached 13% and the runnable queue reached 16 on four cores. The
isolated API peaked around 3.0 OCPUs and only 182 MiB RSS. PostgreSQL peaked near
17% of one CPU and 84 MiB. Memory was not the constraint; API CPU scheduling was.

Because production and the isolated project shared the host, these results are
conservative and also show why future capacity tests must run only in a quiet
window. Production services remained healthy and the production queue remained
zero.

## Operating limits

- **Safe planning limit:** 50 simultaneously active dashboard curators. This
  retains approximately 33% p95 latency headroom and avoids the throughput
  plateau's steepest queueing region.
- **Observed edge:** 70 active curators. Do not advertise this as normal capacity;
  its p95 margin was only 10 ms.
- **Measured failure point:** 80 active curators breached the p95 SLO.
- **Real ML limit remains:** two concurrent jobs per worker and approximately
  2,700 representative jobs/day/worker with operational headroom. Dashboard VUs
  do not imply 50 simultaneous ML jobs.
- **Write acceptance remains:** two submissions/second without shedding in the
  prior isolated write benchmark.

## Docker disk interpretation

Post-cleanup production state was:

- images: approximately 10.15 GB;
- persistent local volumes: approximately 3.98 GB;
- Docker build cache: 12.22 GB, all currently reclaimable;
- root filesystem: 67% used, approximately 15 GB available.

`Reclaimable` does not mean already freed. The 12.22 GB build cache still occupies
disk and can accelerate later image builds. Pruning it would likely reduce root
use to roughly 41%, but forces expensive ML image layers to rebuild. No prune was
performed during this assessment. Benchmark cleanup removed only the disposable
`mh-capacity` resources.

At the current 67%, there is no immediate need for destructive cleanup. At the
70% warning threshold, inspect the daily component report before deciding. If
cache is the cause, prune old build cache during a maintenance window; do not
delete named application volumes or the retained current/previous KB releases.

## OCI resize assessment

Official OCI documentation lists `VM.Standard.A1.Flex` as technically flexible
from 1 to 76 OCPUs and up to 472 GB memory, subject to image compatibility,
tenancy service limits, regional capacity, and billing. A shape change reboots a
running instance, so it requires a maintenance window and verified backup.

The current published Always Free allowance is 2 A1 OCPUs and 12 GB memory total.
This host reports 4 OCPUs and 24 GB, so repository and instance metadata cannot
establish that it is free; the billing console, tenancy type, credits, and any
grandfathering must be checked before resizing or quoting cost.

CPU is the measured bottleneck and memory is ample. If sustained active curator
concurrency approaches 50, first confirm production metrics over multiple days.
If resizing is approved, test 6 or 8 OCPUs while retaining 24 GB memory; adding
memory alone is unlikely to improve dashboard latency. Re-run the same ladder
after resizing before changing the published limit.

OCI supports online boot/block-volume expansion but not shrinking. After an
increase, the guest partition and filesystem must be grown. The current 50 GB
boot disk does not need expansion while reclaimable cache explains most pressure.
Official Always Free block storage totals 200 GB across boot and block volumes,
but actual tenancy allocation and billing must be confirmed first.

## Reproduction

Use the isolated overrides and distinct-user profile only:

```text
docker compose -p mh-capacity -f docker-compose.yml -f docker-compose.loadtest.yml ...
k6 run load/k6/multiuser.js -e VUS=50 -e USER_COUNT=50 -e HOLD=45s
```

Set `CAPACITY_TEST_MODE=1` when running `python -m scripts.seed_load_users` and
`python -m scripts.seed_load_studies`.
Never point the profile at production accounts or production PostgreSQL/Redis
volumes. Destroy the project with `down -v --remove-orphans` after each run.