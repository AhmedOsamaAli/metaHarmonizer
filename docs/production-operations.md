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

## Reported capacity and automatic cleanup

Every check and every alert reports the current sizes, not only the threshold
that was crossed: filesystem used percentage, used and total bytes, free bytes,
total Docker usage, and reclaimable Docker usage. Alerts append a
`Current capacity:` line, so a warning always states where storage actually
stands.

When the filesystem reaches the warning threshold, the check reclaims storage
before assessing thresholds: dangling images and build cache older than the
configured age are removed. If the filesystem is still at or above the threshold
afterwards, the build cache is trimmed to a fixed budget, because a large recent
cache is usually what consumes the space. Tagged images are deliberately kept so
the previously deployed release remains available for rollback. The amount freed
is recorded in the check, the alert, and the daily report.

| Setting | Default | Purpose |
|---|---|---|
| `OPS_AUTO_PRUNE` | `1` | Set `0` to disable automatic reclamation |
| `OPS_PRUNE_THRESHOLD_PERCENT` | `70` | Filesystem use that triggers reclamation |
| `OPS_PRUNE_COOLDOWN_HOURS` | `6` | Minimum interval between automatic runs |
| `OPS_BUILD_CACHE_MAX_AGE_HOURS` | `168` | Build cache older than this is removed first |
| `OPS_BUILD_CACHE_KEEP_GB` | `4` | Build-cache budget kept when trimming is escalated |

Reclaim manually at any time:

```bash
python3 scripts/production_report.py prune
```

## Registration control

Close or reopen new-account registration in one command. The script edits
`ALLOWED_EMAIL_DOMAINS`, recreates the API, confirms the running container took
the new value, and checks public health. If any step fails it restores the
previous setting automatically.

```bash
./scripts/registration_mode.sh status
./scripts/registration_mode.sh close                      # invite-only
./scripts/registration_mode.sh open --domains example.org # named domains
./scripts/registration_mode.sh open --domains '*'         # any verified address
```

Closing registration stops new self-registrations from being approved; people
can still submit the form, but no new account becomes usable without an
administrator approving it. It does **not** sign out or disable existing
accounts. To remove access for an existing user, deactivate that account in the
admin area.

The previous value is kept next to the environment file as
`.env.registration-backup`. That file contains production secrets, so it is
git-ignored and must stay on the host with the same permissions as `.env`.

Verified on 2026-08-19: closing switched the running API to invite-only and
reopening restored `*`, with the API healthy and public health returning 200 at
each step.

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

Production uses a Slack-compatible incoming webhook in the host-only mode-`0600`
configuration. The primary operator is Ahmed Osama Ali and the secondary
operator is Dr. Sehyun Oh. Critical alerts require acknowledgement within 15
minutes and secondary escalation after a further 15 minutes; warnings are
reviewed within four hours. See
`docs/operational-alert-drill-2026-08-19.md` for delivered evidence.

Before declaring operational alerting complete, record:

1. Primary and secondary on-call recipients.
2. Who owns the webhook/provider and its recovery credentials.
3. Expected acknowledgement and escalation times.
4. Delivered test alerts for health, 5xx, queue depth, failed jobs, disk, KB
   updater failure, and stale/failed backup.
5. A quarterly recipient and recovery-access review.

Encrypted off-host backup and clean restore passed on 2026-08-17. Production now
uses `OPS_REQUIRE_BACKUP=1`, so stale or failed backup state is critical. See
`docs/backup-restore-drill-2026-08-17.md`.

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