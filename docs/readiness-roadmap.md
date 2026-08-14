# Production Readiness Roadmap

This is the current provider-neutral closure plan for moving from public beta to an institution-operated service. A gap stays here until its evidence is linked from the verification response.

## Engineering work requiring no external credentials

| Priority | Work | Completion evidence |
| --- | --- | --- |
| P0 | ✅ Generate CycloneDX SBOMs for API and web images in CI and retain them with each release | Hosted run `31279555556` uploaded both CycloneDX 1.7 files for 90 days and passed the full image/runtime smoke; downloaded artifact counts: API 273, web 15; `v*` releases retain both permanently |
| P0 | ✅ Document and exercise application rollback, including database compatibility rules | `docs/rollback-drill-2026-08-09.md`: 42-second exact-revision rollback, migration guard, health checks, authenticated login, automatic recovery, and verified roll-forward |
| P0 | ✅ Document rotation for JWT, database, email, backup, TLS-contact, SSH, and federation credentials | `docs/credential-rotation.md` and dated drill evidence cover all credential classes; JWT/backup/federation tests, disposable PostgreSQL rotation, Caddy validation, and SSH overlap passed; provider-owner acceptance remains separately tracked |
| P1 | ✅ Add a Sentry `before_send` scrubber and synthetic sensitive-data tests | `backend/tests/unit/test_sentry.py` proves request bodies, credentials, filenames, emails, patient/sample identifiers, raw values, exception messages, and breadcrumbs are filtered while operational tags and stack source locations remain; full backend suite: 213 passed, 7 skipped |
| P1 | ✅ Add a versioned mapping benchmark and fail KB refresh on accuracy regression | Hosted finalize run `31837168909` restored checkpoint `31709274076`, passed offline-bundle superset verification and the enforced 200-query gate, retained before/after row and JSON evidence, and republished `kb-latest`. Match rate remained 100% and exact cross-ontology label accuracy remained 31% (62/200); candidate SHA `46b97de7…`. |
| P1 | ✅ Establish capacity limits with distinct-user, upload/job, and real-ML tests | `docs/capacity-report-2026-08-13.md` and `docs/capacity-report-2026-08-15.md`: 80 distinct curator breakpoint ladder plus write and real-engine probes; safe limits: 50 active dashboard curators, 2 accepted submissions/s without shedding, 2 concurrent ML jobs/worker, planning ceiling 2,700 representative jobs/day, and 70%/85% disk warning/stop thresholds |
| P1 | ✅ Define evidence-based public-beta service objectives | `docs/service-level-objectives.md`: 99% monthly availability; dashboard p95 <=750 ms/p99 <=1.5 s at 50 users; zero controlled-fixture errors; warm harmonization p95 <=60 s; queue/storage safeguards and explicitly pending RPO/RTO |
| P1 | ✅ Document phased API, host, storage, and ML expansion | `docs/scaling-plan.md`: measured triggers; OCI 6/8-OCPU decision; API replica prerequisites; same-host ML retest; remote-worker object-storage/network/KB requirements; HA and ARM/GPU limitations |
| P1 | ✅ Add coverage reporting and an agreed minimum gate | Measured baselines: backend 63.21% over all `app/`; frontend 5.16% lines/statements, 23.43% functions, 57.81% branches over all `src/`. Hosted run `31712299291` enforced backend 60% and frontend 5%/5%/20%/50%; all protected checks passed and retained backend XML/HTML (535,546 bytes) plus frontend LCOV/JSON/HTML (365,664 bytes) artifacts for 30 days. |
| P2 | Add intentional `robots.txt`/sitemap behavior and link the beta when approved | Public indexing behavior matches the selected policy |
| P2 | ✅ Publish a standalone curator manual | `docs/curator-guide.md` covers de-identified upload, run modes, schema and ontology decisions, smart/batch review, quality readiness, exports, completion, troubleshooting, and privacy-safe support. Independent usability remains separately tracked below. |

## Work requiring service credentials or owner decisions

| Priority | Work | Needed input | Completion evidence |
| --- | --- | --- | --- |
| P0 | Activate encrypted off-host backups and perform a clean restore drill | S3-compatible bucket, endpoint, access-key ID, secret key | Scheduled backup, retained object, clean restore, application verification |
| P0 | Complete operational alert delivery | Local five-minute checks and daily growth reports are implemented; provide an alert webhook, dedicated metrics token, and accountable primary/secondary recipients | Delivered test alerts for health, 5xx, queue depth, failed jobs, disk, KB updater failure, and stale backup; acknowledged escalation drill |
| P0 | Complete ownership and recovery inventory | Oracle/cloud, registrar/DNS, GitHub, Resend, SSH, database, recovery and 2FA owners | Two authorized administrators and tested recovery path per service |
| P1 | Run authenticated browser journey in hosted CI | Dedicated non-production E2E account | Playwright journey passes without personal credentials |
| P1 | Decide registration/indexing/GA policy | Institution-approved public-access policy | Configuration and documentation match the decision |
| P1 | Independent curator usability exercise | Curator not involved in development | Completed task record, feedback, and resolved blocking issues |
| P1 | Confirm cost and migration decision | Billing-console evidence and institutional hosting requirements | Signed continue/migrate decision with target budget and owner |

## Capacity expansion decision path

| Order | Trigger or decision | Action | Completion evidence |
|---:|---|---|---|
| 1 | Owner decision now | Verify OCI tenancy/billing, current 4-OCPU charge status, service limits, and prices/availability for 6 OCPU/24 GB and 8 OCPU/24 GB | Redacted billing/limits evidence and signed no-change/resize decision |
| 2 | Before any resize | Activate encrypted off-host backup and pass a clean restore drill | Retained backup, clean restore, application verification |
| 3 | Sustained >40 active users or p95 >600 ms | Resize CPU first; test two API processes/replicas; do not add memory without measured need | Repeat 50-80 user ladder, mixed-load test, replica-failure drill, rollback |
| 4 | Sustained queue wait/worker CPU saturation | Move uploads to S3/R2, deploy a private remote worker with the same image/KB SHA | Object lifecycle tests, private connectivity, 1/2-worker benchmark, worker-loss drill |
| 5 | Institution requires HA | External load balancer plus replicated/managed stateful services and external monitoring | Documented RPO/RTO, failover drill, on-call delivery and ownership |

The detailed plan and limitations are in `docs/scaling-plan.md`. No expansion is
automatic, and same-host worker scaling is not accepted as additional ML capacity
without a new real-engine benchmark.

## External/upstream constraints

- The pinned Python base currently has high/critical Debian advisories for which no fixed package version exists. CI blocks every fixable high/critical OS finding and Dependabot tracks base digest updates.
- Public React Router 6 has no compatible release resolving all reported moderate advisories. Dynamic navigation is constrained by an application-level internal-path guard; a Router 7 migration remains a separately tested major upgrade.

## Portability rule

Application behavior is defined by Dockerfiles, Compose files, environment variables, health checks, and one-shot operational commands. Provider-specific concerns are adapters only:

- DNS may be hosted by any provider.
- Caddy handles ACME-compatible public TLS.
- Backups target any S3-compatible object store.
- Backup scheduling may use systemd, cron, Kubernetes CronJob, Nomad, or a managed scheduler.
- Secrets may come from a mode-0600 environment file or the target platform's secret manager.
- A migration transfers PostgreSQL, persistent object/upload data, the KB/model bundle, configuration, and DNS; it does not require application code changes.

## Dependency update policy

- Dependabot creates one grouped patch/minor PR per ecosystem each week.
- Patch/minor PRs receive the `automerge` label and queue for squash merge only after every protected CI and security check passes on the latest `main`.
- Merged branches are deleted automatically.
- Major upgrades are not opened automatically. They are added to the engineering roadmap, tested deliberately (including migration notes and real-engine/browser coverage where relevant), and merged manually.
- Failed or superseded automation PRs are closed rather than accumulated or merged with partial checks.
