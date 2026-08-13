# Capacity Report - 2026-08-13

## Scope

Tests ran on an isolated Docker Compose project (`mh-capacity`) using separate
PostgreSQL, Redis, upload, and cache volumes. No production endpoint or data was
used. API throughput used `ENGINE_IMPL=mock`; real-engine measurements used the
offline local engine/KB separately so API and ML limits are not conflated.

Host: Windows Docker Desktop with 20 CPUs and approximately 31.2 GiB allocated
memory. These results define a conservative operating envelope for this host
shape, not a universal cloud-instance guarantee.

Read SLO: less than 1% failed requests, more than 99% checks, p95 below 800 ms,
and p99 below 2 seconds.

## Curator read capacity

Each iteration used one shared authenticated token and executed the real UI
fan-out: studies, target schemas, review queue, quality, and mappings. The
capacity profile raised the normal per-user abuse-control limit so it measured
API/PostgreSQL/Redis capacity rather than the 600-request/minute user quota.

| Virtual users | Requests | p95 | Failures | Checks | Result |
| ---: | ---: | ---: | ---: | ---: | --- |
| 10 | 2,771 | 111 ms | 0% | 100% | pass |
| 15 | 3,991 | 169 ms | 0% | 100% | pass |
| 20 | 4,401 | 534 ms | 0% | 100% | pass |
| 25 | 4,596 | 1,083 ms | 0% | 100% | fail p95 SLO |

At 20 VUs, the API peaked at 128.8 MiB and 98.8% CPU; PostgreSQL peaked at
80.4 MiB/36.4%, Redis at 7.3 MiB/6.1%, and the mock worker at 178.8 MiB. The
safe read recommendation is **20 concurrent active curators**. Twenty-five
remains functionally correct but is outside the latency objective.

## Upload and queue acceptance

The write profile submitted unique tiny CSV files through the real upload,
validation, database, queue, and worker paths with the mock engine.

| Arrival rate | Attempts | Accepted | User 429 | Queue 503 | p95 | Result |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2/s for 30s | 60 | 60 | 0 | 0 | 99 ms | no shedding |
| 5/s for 30s | 151 | 147 | 4 | 0 | 98 ms | per-user guard active |

The highest tested no-shedding write rate is **2 submissions/second**. This is
172,800 accepted submissions/day only as an API/queue upper bound with a mock
engine; it is not a real-ML jobs/day claim. The configured per-user maximum of
three active jobs correctly sheds bursts with HTTP 429. The queue drained to
zero after both runs.

## Real-engine envelope

- Frozen ontology workload: 200 queries, 9.5 seconds engine time, 23.1 seconds
  cold process wall time, peak approximately 2.0 GiB and 10 logical CPUs.
- Two concurrent ontology workloads: 65.5 seconds aggregate wall time, peak
  approximately 3.0 GiB.
- Four concurrent ontology workloads: 127.9 seconds aggregate wall time, peak
  approximately 4.83 GiB. Throughput improved little over concurrency two while
  individual latency roughly quadrupled.
- Full real harmonization: 707 rows and 141 columns completed successfully in
  31.60 seconds. It added 417,889 bytes of upload storage and approximately
  172 KiB to PostgreSQL.

The enforced default is **two concurrent real ML jobs per worker**
(`WORKER_MAX_JOBS=2`). Four fits memory on this host but is
CPU-contention-bound. Scale worker containers horizontally rather than raising
per-process concurrency without another benchmark. At the measured
31.60-second representative-job duration,
two continuously busy slots imply a theoretical 5,468 jobs/day; apply a 50%
operational headroom factor for a planning limit of **2,700 representative
jobs/day per worker**. Larger or ontology-heavy studies can take longer, so
queue latency and RSS must still be monitored.

## Disk thresholds

The 417,889-byte fixture produced approximately 590 KiB combined persistent
growth (upload plus PostgreSQL). A conservative operator threshold is:

- warning at 70% filesystem use;
- stop accepting new uploads at 85%;
- reserve at least 2 GiB for PostgreSQL, temporary exports, migrations, and
  container operations in addition to retained uploads.

The existing 50 MiB server upload cap remains the per-study hard bound. Disk
planning must use retained-study volume and retention policy rather than the
small representative fixture alone.

## Reproduction

Use `docker-compose.loadtest.yml` with project name `mh-capacity`; seed one
verified account and one completed study so the read fan-out is exercised. Run
the k6 profiles with `--summary-export`, then summarize them with:

```powershell
$env:CAPACITY_TEST_JWT_SECRET = '<random value of at least 32 bytes>'
./load/summarize.ps1 -ResultsDirectory path/to/results
```

Destroy the isolated stack and volumes after collection:

```powershell
docker compose -p mh-capacity -f docker-compose.yml -f docker-compose.loadtest.yml down -v
```