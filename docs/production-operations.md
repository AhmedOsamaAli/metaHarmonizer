# Production operations, alerts, and growth

## Current baseline

Measured on the Oracle production host on 2026-08-15. The host has a fixed
45 GiB root filesystem; ordinary traffic does not autoscale compute or cost.

| Measure | Current value | Planning significance |
|---|---:|---|
| Root filesystem | 66.4% used, 14.8 GiB free | Below the 70% warning threshold |
| Reclaimable Docker build cache | 11.4 GiB (`docker system df`: 12.22 GB decimal) | Still occupies disk; primary cleanup opportunity, not user data |
| Docker images | 9.4 GiB | Large ML runtime; API and worker share one image |
| Current KB release volumes | 1.63 GiB | Active ontology/corpus/model snapshot |
| Previous KB release volumes | 1.63 GiB | Retained for rollback |
| PostgreSQL volume | 74.7 MiB | Database itself reports 10.9 MB of logical data |
| Redis volume | 26.6 MiB | Queue depth was zero |
| Uploads | 1.7 MiB | Seven studies at measurement time |
| Schema versions and aliases | 8.3 MiB | Small relative to ML assets |
| Failed work | 0 recent, 0 unresolved | No current job alert |

The current KB refresh changed the bundle SHA but barely changed its installed
footprint: the current three KB volumes are approximately 400 KiB larger than
the previous release. Quarterly growth must therefore be measured from each
release rather than inferred from ontology term count alone.

`Reclaimable` means Docker may safely discard unused build cache; it does not
mean the space has already been freed. No automatic cache prune runs in
production. See `docs/capacity-report-2026-08-15.md` for the measured
distinct-user breakpoint and OCI resize assessment.

## Release headroom

The updater keeps the current and previous SHA-specific KB volume sets. During
a refresh it also holds the downloaded bundle and a staged third release before
pruning old retained volumes. Reserve at least 3.5 GiB beyond steady state for
that transient operation, plus the existing 2 GiB PostgreSQL/export/migration
reserve.

At the measured baseline, a refresh has sufficient headroom. Do not start an
automatic refresh at or above the 85% stop threshold. At 70%, investigate the
growth report first; reclaimable build cache is distinct from persistent user
or KB data and can explain high filesystem use without implying product growth.

## Automated checks and reports

Two systemd timers run independently of the application containers:

| Timer | Frequency | Output |
|---|---|---|
| `metaharmonizer-ops-check.timer` | Every 5 minutes | Health/threshold JSON and deduplicated alerts |
| `metaharmonizer-ops-report.timer` | Daily at 04:00 UTC | JSON snapshot and Markdown capacity report |

Reports are retained under
`/home/ubuntu/.local/state/metaharmonizer/operations/`. Forecasts begin after
at least 12 hours of snapshots and estimate days to 70% and 85% from observed
whole-filesystem growth. Whole-filesystem growth is deliberately conservative;
the component table separates KB releases, uploads, PostgreSQL, Redis, images,
volumes, and reclaimable build cache.

Install or update the units:

```bash
sudo cp deploy/systemd/metaharmonizer-ops-* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now metaharmonizer-ops-check.timer
sudo systemctl enable --now metaharmonizer-ops-report.timer
```

Inspect the current report:

```bash
cat ~/.local/state/metaharmonizer/operations/latest-report.md
systemctl list-timers 'metaharmonizer-ops-*' --no-pager
journalctl -u metaharmonizer-ops-check.service -n 50 --no-pager
```

## Thresholds

| Signal | Warning | Critical/action |
|---|---:|---:|
| Root filesystem | 70% | 85%; stop new uploads |
| Queue depth | 160 | 200; API capacity limit |
| Distinct authenticated users active in five minutes | 40 | 50; warning only, investigate measured capacity and do not reject users automatically |
| Public health | - | Any non-200 response |
| API/worker/PostgreSQL/Redis | - | Missing or unhealthy |
| Failed jobs | Any in 24 hours | Any unresolved dead-letter failure |
| HTTP 5xx | - | Any increase between five-minute checks |
| KB updater | Timer inactive | Investigate updater service result |
| Backup | Warning until activation | Critical after restore drill and `OPS_REQUIRE_BACKUP=1` |

HTTP 5xx metrics remain admin-scoped. Create a dedicated API token and place it
only in `/home/ubuntu/.config/metaharmonizer/ops-monitor.env` as
`OPS_METRICS_BEARER_TOKEN`; do not make `/metrics` public.

The active-user count is a rolling aggregate from authenticated requests. It is
not total registered accounts, open refresh sessions, or exact instantaneous
concurrency. Use it with latency, request rate, CPU, queue, and job metrics.

## Delivery and ownership

Copy `deploy/ops-monitor.env.example` to the host-only path above with mode
`0600`. `OPS_ALERT_WEBHOOK_URL` accepts a Slack-compatible incoming webhook.
Without a webhook, checks and reports still run and are retained locally, but
there is no defensible claim that someone will be notified at 3 a.m.

Before declaring operational alerting complete, record:

1. Primary and secondary on-call recipients.
2. Who owns the webhook/provider and its recovery credentials.
3. Expected acknowledgement and escalation times.
4. Delivered test alerts for health, 5xx, queue depth, failed jobs, disk, KB
   updater failure, and stale/failed backup.
5. A quarterly recipient and recovery-access review.

Backups remain a separate P0 gap. Keep `OPS_REQUIRE_BACKUP=0` until an encrypted
off-host backup and clean restore drill pass; then enable it so stale or failed
backup state becomes critical.

## Cost and migration interpretation

The host is fixed capacity, so growth does not automatically double spend.
Costs change only when an owner enlarges/replaces the VM, adds workers or block
storage, activates object storage, or adopts paid monitoring/email services.
Use the daily forecast and the measured 50-active-curator, two-job worker limit
to trigger a documented continue/resize/migrate decision; do not infer cost
from term count, study count, or queue submissions alone.

Measured triggers and the phased API/ML expansion procedure are defined in
`docs/scaling-plan.md`. CPU expansion comes before memory expansion; remote ML
workers require object storage and private data-service connectivity first.