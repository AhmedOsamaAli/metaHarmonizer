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

## Profiles

| Profile             | What it does                                              | Typical use            |
| ------------------- | -------------------------------------------------------- | ---------------------- |
| `smoke`             | 1 VU, 5 iterations — proves the flow + thresholds work   | first, and in CI       |
| `load`              | ramp to `VUS`, hold, ramp down — steady curator traffic  | capacity vs SLO        |
| `stress`            | ramp to 8× `VUS` — find the knee / graceful degradation  | breaking point         |
| `soak`              | hold `VUS` for `SOAK` (default 30m) — leak detection     | memory/connection leak |
| `harmonize_submit`  | fixed arrival-rate submits (unique files) — write path   | enqueue + backpressure |

The read profiles exercise the real curator hot path: `login` → `GET /studies`
→ per-study `review-queue` + `quality` + `mappings`, plus the `/readyz` probe.
Login happens **once** in `setup()` and the token is reused, so results reflect
the read path rather than Argon2 password hashing.

## Run it

```powershell
# convenience wrapper (PowerShell)
./load/run.ps1 -Suite smoke -BaseUrl http://localhost:8000 -Email admin@example.com -Password 'ChangeMe!2026'
./load/run.ps1 -Suite load  -Vus 50 -Hold 5m
./load/run.ps1 -Suite stress -Vus 25
./load/run.ps1 -Suite soak  -Vus 20            # add -e SOAK=2h via k6 directly for longer
./load/run.ps1 -Suite harmonize -Rate 5 -Duration 2m

# or call k6 directly
k6 run load/k6/load.js -e BASE_URL=http://localhost:8000 -e EMAIL=admin@example.com -e PASSWORD='ChangeMe!2026' -e VUS=50 -e HOLD=5m
```

### Tunables (`-e NAME=value`)

| Var                       | Default                 | Meaning                                  |
| ------------------------- | ----------------------- | ---------------------------------------- |
| `BASE_URL`                | `http://localhost:8000` | API base URL                             |
| `EMAIL` / `PASSWORD`      | seeded admin            | login credentials                        |
| `VUS`                     | `25`                    | target virtual users                     |
| `HOLD`                    | `2m`                    | hold duration at target (load)           |
| `THINK`                   | `1`                     | seconds between iterations per VU        |
| `SOAK`                    | `30m`                   | soak hold duration                       |
| `RATE` / `DURATION`       | `2` / `1m`              | harmonize submits per second + run length|

## SLOs (thresholds)

`load` and `soak` enforce, and **exit non-zero** if breached — so they gate CI:

- `http_req_failed` &lt; **1%**
- `http_req_duration` **p95 &lt; 800 ms**, **p99 &lt; 2 s**
- `checks` &gt; **99%**

Tune these in [k6/lib/config.js](k6/lib/config.js) to your agreed SLOs. `stress`
uses looser limits on purpose — it's there to *find* the ceiling, and to confirm
the app sheds load with `429`/`503` rather than `5xx`.

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
