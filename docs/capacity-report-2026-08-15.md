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

The project-approved public-beta objectives are:

- zero unexpected HTTP failures;
- 100% checks;
- p95 at or below 1 second;
- p99 at or below 2 seconds.

The table is classified against the approved beta SLO in
`docs/service-level-objectives.md`. SLO compliance and safe operating capacity
are separate: safe capacity additionally requires 25% p95 headroom,
non-declining throughput, and resource reserve.

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
| 70 | 11,095 | 100.8 req/s | 790 ms | 858 ms | 0% | 100% | SLO pass; below planning headroom |
| 80 | 10,995 | 98.8 req/s | 945 ms | 991 ms | 0% | 100% | SLO pass; saturation, not safe capacity |

Throughput flattened at approximately 98-101 requests/second from 50 users
onward. At 80 users throughput fell while latency rose, demonstrating CPU queueing
rather than useful scaling. The 80-user rung remained functionally correct but
had only 5.5% p95 headroom and saturated host CPU scheduling. It meets the
approved beta response objective but is not safe operating capacity.

## What “50 users” means

The 50-user planning limit means **50 distinct authenticated curators actively
repeating the measured dashboard workflow at the same time**, with one second
between iterations. It does not mean:

- only 50 accounts may be registered;
- only 50 people may use the system in a day or month;
- 50 browser tabs left idle consume the measured capacity;
- 50 simultaneous uploads or real ML jobs are supported.

No maximum registered-account count was benchmarked. Inactive accounts and
refresh-session rows do not generate request load; their database storage is a
different growth question. The test created 80 accounts only to supply distinct
identities for the concurrency ladder, not to establish an account-count limit.

Normal production HTTP requests are short, so “instantaneous concurrent users”
is not directly observable after a response completes. Production therefore
records the aggregate number of distinct authenticated users seen in the last
five minutes. That rolling count is a scaling signal, not an assertion that all
of those users issued a request in the same millisecond. Open WebSockets count
only users watching live progress and are also not a complete user count.
The rolling set is updated by valid bearer/API-token HTTP requests, including
rate-limit-exempt job polling and WebSocket-ticket creation; a refresh-cookie
request alone is not counted until the client makes an authenticated API call.

## Resource paths and bottlenecks

| Workload/resource | Measured or configured boundary | First bottleneck | Scale action | Evidence not yet available |
|---|---|---|---|---|
| Dashboard reads | 50 active curators safe; 80 meets beta SLO but saturates | API/host CPU and runnable queue | More OCPUs, then test multiple API processes/replicas | Mixed read plus real-ML ladder after resize |
| Registered/inactive users | No tested account maximum | PostgreSQL row/index growth eventually; no current pressure measured | Observe DB size/query plans; archive only with policy | Account-count/storage benchmark |
| Login bursts | Anonymous IP budget 20 requests/minute; account lock after 5 failed attempts | Security controls by design | Do not raise for capacity; use SSO or distributed ingress only after threat review | Multi-site legitimate-login arrival profile |
| Upload acceptance | 2 submissions/second tested without shedding; 3 active jobs/user | Per-user guard, then queue depth | Preserve guards; add workers only when queue age proves need | Mixed large-file arrival test |
| Real ML execution | 2 concurrent jobs/worker; 2,700 representative jobs/day planning | Worker/host CPU; four-way test showed little throughput gain | CPU resize and retest; remote workers after object storage/private networking | Production-shape mixed read/ML benchmark |
| Queue | Warning 160, reject 200 | Configured Redis backpressure | Add verified worker capacity before changing queue limit | Oldest-job wait metric not yet implemented |
| PostgreSQL | Logical DB approximately 10.9 MB at baseline; pool 10 + 20 overflow/process | Aggregate connection pools when API/workers multiply | Recalculate pools below `max_connections`; tune from observed waits | Connection saturation benchmark |
| Redis | Approximately 26.6 MiB volume; queue zero at baseline | Queue/rate/session operations; no saturation observed | Private central Redis or managed/replicated service for multi-host | Redis latency/failover benchmark |
| Memory | Approximately 20 GB available before load test | Not the dashboard limit; model duplication can change this | Keep 4 GiB reserve; measure per added API/worker process | Multi-process engine RSS measurement |
| Disk | 67% used; 12.22 GB build cache reclaimable; 70%/85% thresholds | Build cache or retained data/KB depending report | Inspect components, prune cache in maintenance, expand volume only when justified | Long-term organic growth after enough daily snapshots |
| Network | Shape reports 4 Gbps; no network saturation observed | Unknown because not reached | Measure before changing network architecture | Bandwidth/connection telemetry under external load |

Values labeled “not yet available” are gaps, not implied capacity.

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
  retains approximately 29% p95 latency headroom and avoids the throughput
  plateau's steepest queueing region.
- **Observed planning edge:** 60 active curators, measured at p95 610 ms and p99
  646 ms.
- **Saturation evidence:** 80 users still met the beta SLO, but throughput fell,
  p95 headroom was only 5.5%, host idle reached 13%, and run queue reached 16.
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