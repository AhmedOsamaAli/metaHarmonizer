# Load & stress testing (k6)

Capacity, latency, and soak testing for the MetaHarmonizer API with
[k6](https://k6.io). These profiles answer *"how does the stack behave under
concurrent load, and where does it break?"* before a production deploy.

## Install k6

```powershell
winget install k6 --source winget      # Windows
# brew install k6                       # macOS
# https://k6.io/docs/get-started/installation/ for others
```

## Point it at a running stack

Any reachable instance works — the Docker compose stack, a staging box, or the
dev API. Bring one up (see [DEPLOY.md](../DEPLOY.md)) and note its URL + a
curator/admin login.

> Run capacity tests against a stack using **`ENGINE_IMPL=mock`**. The real
> engine loads ~700 MB of models and does heavy ML per harmonize — great for
> accuracy benchmarking (`scripts/run_benchmarks.ps1`), wrong for measuring API
> throughput.

Use the isolated profile rather than an existing dev or production database:

```powershell
$env:CAPACITY_TEST_JWT_SECRET = '<random value of at least 32 bytes>'
if (-not (Test-Path .env)) { New-Item .env -ItemType File | Out-Null }
docker compose -p mh-capacity -f docker-compose.yml -f docker-compose.loadtest.yml `
  up -d --no-build postgres redis volume-init api worker
```

It exposes only the test API on `http://localhost:18000`, uses separate named
volumes, forces the mock engine, and raises the per-user rate limit so a shared
load-test token measures API capacity rather than the normal abuse-control cap.

## Profiles

| Profile             | What it does                                              | Typical use            |
| ------------------- | -------------------------------------------------------- | ---------------------- |
| `smoke`             | 1 VU, 5 iterations — proves the flow + thresholds work   | first, and in CI       |
| `load`              | ramp to `VUS`, hold, ramp down — steady curator traffic  | capacity vs SLO        |
| `multiuser`         | one isolated account/token per VU and owner-scoped reads | distinct-user capacity |
| `stress`            | ramp to 8× `VUS` — find the knee / graceful degradation  | breaking point         |
| `soak`              | hold `VUS` for `SOAK` (default 30m) — leak detection     | memory/connection leak |
| `harmonize_submit`  | fixed arrival-rate submits (unique files) — write path   | enqueue + backpressure |

The read profiles exercise the real curator hot path: `login` → `GET /studies`
→ per-study `review-queue` + `quality` + `mappings`, plus the `/readyz` probe.
Login happens **once** in `setup()` and the token is reused, so results reflect
the read path rather than Argon2 password hashing.

For `multiuser`, seed accounts only into the isolated `mh-capacity` database:

```powershell
$env:LOAD_TEST_PASSWORD = '<random isolated password>'
docker compose -p mh-capacity -f docker-compose.yml -f docker-compose.loadtest.yml `
  exec -e CAPACITY_TEST_MODE=1 -e LOAD_TEST_PASSWORD=$env:LOAD_TEST_PASSWORD `
  api python -m scripts.seed_load_users --count 50
docker compose -p mh-capacity -f docker-compose.yml -f docker-compose.loadtest.yml `
  exec -e CAPACITY_TEST_MODE=1 -e LOAD_TEST_PASSWORD=$env:LOAD_TEST_PASSWORD `
  api python -m scripts.seed_load_studies --count 50

docker run --rm --network host `
  -e "PASSWORD=$env:LOAD_TEST_PASSWORD" `
  -v "${PWD}/load/k6:/scripts:ro" grafana/k6:latest run `
  -e BASE_URL=http://localhost:18000 -e VUS=50 -e USER_COUNT=50 `
  /scripts/multiuser.js
```

Never run either seeder against production. They refuse to run unless
`CAPACITY_TEST_MODE=1`, but the operator must also verify the Compose project
is `mh-capacity` and uses the dedicated `mh_capacity_*` volumes.

## Run it

```powershell
# convenience wrapper (PowerShell)
$env:LOAD_TEST_PASSWORD = '<load-test password>'
./load/run.ps1 -Suite smoke -BaseUrl http://localhost:8000 -Email admin@example.com
./load/run.ps1 -Suite load  -Vus 50 -Hold 5m
./load/run.ps1 -Suite stress -Vus 25
./load/run.ps1 -Suite soak  -Vus 20            # add -e SOAK=2h via k6 directly for longer
./load/run.ps1 -Suite harmonize -Rate 5 -Duration 2m
./load/run.ps1 -Suite soak -Vus 20 -Hold 30m -SummaryExport results/soak.json

# or call k6 directly
k6 run load/k6/load.js -e BASE_URL=http://localhost:8000 -e EMAIL=admin@example.com -e PASSWORD='ChangeMe!2026' -e VUS=50 -e HOLD=5m
```

### Tunables (`-e NAME=value`)

| Var                       | Default                 | Meaning                                  |
| ------------------------- | ----------------------- | ---------------------------------------- |
| `BASE_URL`                | `http://localhost:8000` | API base URL                             |
| `EMAIL` / `PASSWORD`      | seeded admin            | login credentials                        |
| `VUS`                     | `25`                    | target virtual users                     |
| `USER_COUNT`              | `VUS`                   | distinct accounts used by `multiuser`    |
| `HOLD`                    | `2m`                    | hold duration at target (load)           |
| `THINK`                   | `1`                     | seconds between iterations per VU        |
| `SOAK`                    | `30m`                   | soak hold duration                       |
| `RATE` / `DURATION`       | `2` / `1m`              | harmonize submits per second + run length|

`-Hold` controls both the load hold and soak hold. Use `-SummaryExport` for a
compact, durable k6 summary; `-Out json=...` records the much larger time series.

## SLOs (thresholds)

`load`, `multiuser`, and `soak` enforce the public-beta dashboard objectives and
**exit non-zero** if breached:

- `http_req_failed` = **0%** in the deterministic isolated fixture
- `http_req_duration` **p95 ≤ 750 ms**, **p99 ≤ 1.5 s**
- `checks` = **100%**

Smoke and write-load fixtures are strict for the same reason: every expected
status is known, including intentional `429`/`503` backpressure. The rationale
and current evidence are in
[service-level-objectives.md](../docs/service-level-objectives.md). Do not tune
thresholds merely to make a run pass. `stress` is observational and has no
pass/fail threshold; it locates the knee and records whether degradation is
intentional `429`/`503` rather than unexpected `5xx`.

## Reading the output

- `http_req_duration` (avg / p95 / p99) — latency budget.
- `http_req_failed` — error rate.
- per-endpoint metrics via the `name` tag (`studies`, `review-queue`, `quality`, …).
- Export raw results with `-Out json=results.json` (or `--out`), or stream to
  InfluxDB/Prometheus for dashboards.

## CI

`smoke` is safe to run in CI against the `deploy-smoke` compose stack (mock
engine) as a fast regression gate. The heavier `load`/`stress`/`soak` profiles
are meant to be run deliberately against a sized staging environment.

Destroy every isolated resource after a deliberate capacity run:

```powershell
docker compose -p mh-capacity -f docker-compose.yml -f docker-compose.loadtest.yml `
  down -v --remove-orphans
```
