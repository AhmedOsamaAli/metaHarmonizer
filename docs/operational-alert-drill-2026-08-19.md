# Operational alert delivery drill - 2026-08-19

## Scope

Production alert delivery was configured through a private Slack incoming
webhook stored only in the host's mode-`0600` operations environment file. A
dedicated read-scoped admin API token was created for the protected Prometheus
endpoint; only its hash is stored in PostgreSQL and its plaintext is host-only.

## Operators and escalation

- Primary operator: Ahmed Osama Ali.
- Secondary operator: Dr. Sehyun Oh.
- Delivery channel: private `#metaharmonizer-alerts` channel in the dedicated
  MetaHarmonizer operations Slack workspace.
- Critical alerts: primary acknowledgement within 15 minutes; escalate to the
  secondary operator if unacknowledged after a further 15 minutes.
- Warning alerts: review within four hours.
- Recipient access and recovery ownership: review quarterly and whenever an
  operator leaves the project.

These are public-service operating targets, not a staffed institutional 24/7
on-call contract.

## Verified delivery

1. The host-only webhook passed structural validation and Slack accepted a
   harmless delivery test.
2. The primary operator confirmed the message appeared in Slack.
3. The secondary operator joined the private channel and acknowledged the drill.
4. One non-disruptive synthetic matrix was delivered for every required signal:
   - public health unavailable;
   - new HTTP 5xx responses;
   - queue depth above warning threshold;
   - unresolved failed job;
   - disk above warning threshold;
   - KB updater failure/inactivity;
   - stale/failed backup.
5. Production remained healthy during the synthetic drill.

The synthetic matrix validated the shared delivery and acknowledgement path
without intentionally damaging production. Signal classification is covered by
the operations-report unit suite; live checks exercise public/service health,
disk, queue, jobs, KB updater, backup freshness, and authenticated metrics.

## Current production state

- Five-minute operations timer: enabled and active.
- Daily capacity report timer: enabled and active.
- Authenticated `/metrics`: HTTP 200 with Prometheus exposition.
- Encrypted backup timer: enabled and active with strict 36-hour freshness
  monitoring.
- Disk maintenance reduced root usage from 71% to 58% without deleting
  application volumes.
- After maintenance, operations checks reported no active issues.

## Credential handling

- Webhook and metrics token are absent from Git and logs.
- Host-only operations configuration is mode `0600`.
- The first webhook pasted into chat was revoked before use; the replacement was
  transferred through a temporary local file and both temporary copies were
  deleted.
- Rotate the Slack webhook immediately if it is exposed and repeat this drill.

## Result

**Pass.** Local detection, authenticated 5xx collection, external Slack
delivery, primary/secondary receipt, the seven-signal synthetic matrix, and
escalation expectations are verified for public operation.