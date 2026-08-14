# Public beta service objectives

## Purpose and status

These objectives replace the undocumented 800 ms p95 / 2 second p99 load-test
defaults. They are engineering objectives for the public beta, grounded in the
curator workflow, measured production-shape behavior, and the existing project
acceptance criteria. Institutional owners may tighten them after observing real
traffic, but changes require a dated decision and a repeated capacity test.

## Objectives

| Surface | SLI | Public beta objective | Rationale |
|---|---|---|---|
| Availability | Successful five-minute public `/healthz` checks | 99% per calendar month, excluding announced maintenance | Existing project objective; permits approximately 7h 18m unavailable in a 30.44-day month while the service has no HA/failover |
| Dashboard API | Request duration for the authenticated curator read fan-out at 50 active users | p95 at or below 750 ms; p99 at or below 1.5 s | Keeps the normal interaction within a one-second budget after reserving 250 ms for network/browser rendering; keeps tail interactions within two seconds after the same client allowance |
| Dashboard correctness | Expected statuses/checks in the controlled capacity fixture | 100% checks and zero unexpected HTTP failures | Every request in the deterministic isolated fixture has a known expected response; allowing test errors would hide capacity defects |
| Warm harmonization | End-to-end duration for the representative 200-column workload | p95 at or below 60 seconds | Existing project acceptance criterion; work is asynchronous and exposes progress rather than blocking the dashboard |
| Queue protection | Pending arq jobs | Warning at 160; reject at 200 | 80% early-warning point and the configured hard backpressure limit |
| Storage protection | Root filesystem used | Warning at 70%; stop new uploads at 85% | Leaves room for a staged KB release and the 2 GiB database/export/migration reserve |

The 50-user target is a capacity planning load, not a forecast of adoption and
not permission to run 50 simultaneous ML jobs. Real ML remains limited to two
concurrent jobs per worker until a new benchmark proves a larger value.

## Measurement

- Dashboard latency is measured by `load/k6/multiuser.js` against an isolated
  stack with one account and one review-ready study per VU.
- Availability is sampled every five minutes by
  `metaharmonizer-ops-check.timer`. An external monitor is still required to
  detect host/network failure when the VM itself cannot run the check.
- HTTP 5xx deltas require the host-only metrics bearer token described in
  `docs/production-operations.md`.
- Harmonization duration is measured separately with the real engine; mock
  engine API tests cannot establish ML latency.

## Current evidence

The 2026-08-15 production-shape test measured 50 users at p95 536 ms with no
failures. Sixty users measured p95 610 ms and p99 646 ms. Seventy users measured
p95 790 ms and therefore exceeded the adopted 750 ms p95 objective; 80 users
measured p95 945 ms. The safe planning limit remains 50 users.

The representative 707-row/141-column real harmonization completed in 31.60
seconds. This supports, but does not fully prove, the 200-column p95 objective;
a repeated 200-column sample set is required before claiming that SLO as met.

## Not yet defined

Backup RPO/RTO, incident acknowledgement time, and recovery time are intentionally
unset until the encrypted off-host restore drill and ownership exercise are
complete. Publishing invented targets before those drills would not create a
recoverable service.