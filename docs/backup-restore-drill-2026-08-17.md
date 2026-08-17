# Encrypted backup and clean restore drill - 2026-08-17

## Scope

The production PostgreSQL database was backed up to a dedicated private
Cloudflare R2 bucket, encrypted on the host with AES-256-GCM, restored into a
new scratch database, validated through a disposable API process, and removed.
Production was never a restore target and remained healthy throughout.

## Backup

- Dedicated bucket: `metaharmonizer-backups`.
- Credentials are bucket-scoped and stored only in the production mode-0600
  environment file.
- The 32-byte encryption key is host-only, mode `0600`, and readable by the
  non-root application container UID 1000.
- The systemd backup service completed successfully and wrote its durable
  `last-success` marker only after upload.
- R2 evidence after retention: 1 encrypted object, 133,578 bytes, newest upload
  at 2026-08-17 13:42:20 UTC.
- The next scheduled run was 2026-08-18 02:02:14 UTC.

The retention implementation groups restore points into 7 daily, 4 weekly, and
12 monthly slots. Repeated same-day drills may leave one retained daily object;
this is expected and keeps storage bounded.

## Restore

1. Created `metaharmonizer_restore_test`, separate from production.
2. Downloaded and authenticated/decrypted the newest R2 object with the host-only
   key.
3. Rendered the custom-format archive to SQL, removed only PostgreSQL client's
   unsupported `SET transaction_timeout` compatibility statement, and executed
   the remainder with `ON_ERROR_STOP=1`.
4. Verified the restored Alembic revision.
5. Compared aggregate table counts between production and the restored database:

| Table | Production | Restored |
|---|---:|---:|
| users | 4 | 4 |
| studies | 7 | 7 |
| mappings | 641 | 641 |
| ontology_mappings | 53 | 53 |
| job_runs | 8 | 8 |
| audit_events | 167 | 167 |

6. Started a disposable API against the restored database and verified readiness
   reported PostgreSQL and Redis as `ok`.
7. Removed the disposable API and dropped the scratch database. A final query
   returned zero databases named `metaharmonizer_restore_test`.

## Scheduling and monitoring

- `metaharmonizer-backup.timer` is enabled and active for daily execution near
  02:00 UTC.
- Strict monitoring is enabled with `OPS_REQUIRE_BACKUP=1`.
- The operations check verifies timer activity, service result, and age of the
  success marker; freshness becomes critical after 36 hours.
- After activation the check reported no `backup_*` issues.

## Production safety

- Public `/healthz` returned HTTP 200 after backup and restore.
- API, worker, PostgreSQL, and Redis remained healthy.
- Production was never overwritten and no application volume was removed.
- Root disk remained below the 85% stop threshold; build cache cleanup was kept
  separate from backup data.

## Result

**Pass.** Encrypted off-host backup, clean restore, application readiness,
aggregate data parity, scratch cleanup, daily scheduling, and freshness
monitoring are verified.

Relevant fixes: [`23e5af2`](https://github.com/AhmedOsamaAli/metaHarmonizer/commit/23e5af2)
for PostgreSQL 16 restore compatibility and
[`87ed4b7`](https://github.com/AhmedOsamaAli/metaHarmonizer/commit/87ed4b7)
for durable successful-backup freshness monitoring.