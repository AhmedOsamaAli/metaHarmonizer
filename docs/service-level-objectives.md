# Public beta service objectives

## Purpose and status

These objectives replace the undocumented load-test defaults. They are a
proposed engineering baseline for the public beta, grounded in the curator
workflow, measured production-shape behavior, and existing project acceptance
criteria. They are not institutionally accepted until a named mentor or service
owner approves them using the process below.

## Objectives

| Surface | SLI | Public beta objective | Rationale |
|---|---|---|---|
| Availability | Successful five-minute public `/healthz` checks | 99% per calendar month, excluding announced maintenance | Existing project objective; permits approximately 7h 18m unavailable in a 30.44-day month while the service has no HA/failover |
| Dashboard API | Request duration for the authenticated curator read fan-out | p95 at or below 1 second; p99 at or below 2 seconds | Direct public-beta user-experience target: normal interactions return within one second and rare tail interactions within two seconds |
| Dashboard correctness | Expected statuses/checks in the controlled capacity fixture | 100% checks and zero unexpected HTTP failures | Every request in the deterministic isolated fixture has a known expected response; allowing test errors would hide capacity defects |
| Warm harmonization | End-to-end duration for the representative 200-column workload | p95 at or below 60 seconds | Existing project acceptance criterion; work is asynchronous and exposes progress rather than blocking the dashboard |
| Queue protection | Pending arq jobs | Warning at 160; reject at 200 | 80% early-warning point and the configured hard backpressure limit |
| Storage protection | Root filesystem used | Warning at 70%; stop new uploads at 85% | Leaves room for a staged KB release and the 2 GiB database/export/migration reserve |

Meeting the SLO at a saturation test does not make that load safe. Capacity
planning additionally requires at least 25% p95 headroom, non-declining
throughput, and resource reserve. The 50-user target meets those conditions; it
is not a forecast of adoption or permission to run 50 simultaneous ML jobs.
Real ML remains limited to two concurrent jobs per worker.

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
failures. Sixty users measured p95 610 ms/p99 646 ms, 70 measured p95 790
ms/p99 858 ms, and 80 measured p95 945 ms/p99 991 ms. All measured rungs meet
the proposed beta latency SLO. Eighty users is still not a safe planning load:
throughput declined, host CPU idle reached 13%, and the runnable queue reached
16 on four cores. The safe planning limit remains 50 users.

The representative 707-row/141-column real harmonization completed in 31.60
seconds. This supports, but does not fully prove, the 200-column p95 objective;
a repeated 200-column sample set is required before claiming that SLO as met.

## Approval

SLOs are not sent to Oracle or a standards organization. Approval is a project
governance decision:

1. Send the reviewer a link to this document and the two dated capacity reports.
2. A named mentor/service owner responds in a meeting record, issue, or pull
  request: "Approved as the MetaHarmonizer public-beta SLO through [review date]."
3. Record the approver, approval date, and review date below.
4. Any changed number must include its user rationale and new benchmark evidence;
  thresholds are never loosened solely to make a test pass.

| State | Approver | Approval date | Review date |
|---|---|---|---|
| Proposed; awaiting owner/mentor acceptance | - | - | Three months after approval |

## Not yet defined

Backup RPO/RTO, incident acknowledgement time, and recovery time are intentionally
unset until the encrypted off-host restore drill and ownership exercise are
complete. Publishing invented targets before those drills would not create a
recoverable service.