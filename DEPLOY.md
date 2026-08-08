# Self-hosting MetaHarmonizer

A provider-neutral runbook to stand up a production instance with Docker
Compose on any Linux VM or compatible container host. The stack is **Postgres +
Redis + API + arq worker + Caddy (serving the built SPA)**. Cloud-specific VM,
DNS, firewall, secret-manager, scheduler, and backup-storage setup stays outside
the application boundary.

All production commands below use both Compose files so the development override
is never loaded accidentally:

```bash
export COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml
```

## 1. Requirements

- **Docker** + **Docker Compose v2** on the host.
- **~8 GB RAM**, **2+ CPU cores**, **~15 GB disk** (models + KB + Postgres).
  The embedding models load into RAM and run on CPU — no GPU required.
- A domain name if you want HTTPS (Caddy issues certs automatically).

## 2. Get the code + configure

```bash
git clone https://github.com/AhmedOsamaAli/metaHarmonizer.git
cd metaHarmonizer
cp .env.example .env
```

Edit `.env` — at minimum set these for production:

| Variable                                  | Set to                                                                                |
| ----------------------------------------- | ------------------------------------------------------------------------------------- |
| `JWT_SECRET`                              | a real 32+ byte secret: `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `POSTGRES_PASSWORD`                       | a strong password                                                                     |
| `JOB_MODE`                                | `queue` (so the worker runs harmonizations)                                           |
| `ALLOWED_EMAIL_DOMAINS`                   | your org's email domain(s), comma-separated                                           |
| `CORS_ORIGINS` / `APP_BASE_URL`           | your public URL (e.g. `https://harmonize.example.org`)                                |
| `HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE` | `1` (load models from the seeded cache)                                               |
| `RESEND_API_KEY`                          | for verification/reset email; without it, delivery is skipped without logging tokens  |

The container DSNs for Postgres/Redis are set by compose — you do **not** edit
`DATABASE_URL`/`REDIS_URL` for the Docker path.

## 3. Build the offline bundle (on a networked machine)

The engine needs its knowledge base, ontology corpora, and embedding models.
Build them **once** on a box with internet, then ship the bundle to the host:

```bash
cd backend
python -m scripts.package_kb -o ../kb/kb_offline_bundle.tar.gz
#   --dry-run   to preview contents + size (~0.7 GB models + KB)
#   --no-models to exclude models (if you manage them separately)
```

Copy the whole repo (or just `kb/kb_offline_bundle.tar.gz`) to the host so the
file sits at `./kb/kb_offline_bundle.tar.gz`.

## 4. Seed the KB + models into the stack

```bash
docker compose --profile kb run --rm kb-import
```

This installs the KB, corpus CSVs, and models into the shared `engine_cache`,
`corpus_data`, and `hf_cache` volumes so the API/worker load everything from
disk — the first harmonization never touches the network.

## 5. Start the stack

```bash
docker compose up -d              # postgres, redis, api, worker, caddy, web
docker compose ps                 # all should be healthy
docker compose exec api curl -fsS http://localhost:8000/healthz   # 200 when the API is up
```

Migrations run automatically on API start (`alembic upgrade head`).

## 6. Create the first admin

```bash
SEED_EMAIL=admin@example.org SEED_PASSWORD='ChangeMe!2026' \
  docker compose --profile seed run --rm seed
```

Log in at your domain (or `http://<host>` if no TLS), upload a CSV, and run a
harmonization to confirm the engine loads offline.

## 7. TLS / domain

Set `DOMAIN`, `ACME_EMAIL`, `APP_BASE_URL=https://...`, and
`COOKIE_SECURE=true` in `.env`. `Caddyfile.prod` provisions and renews
certificates automatically. Point the chosen DNS provider's A/AAAA records at
the host and allow inbound TCP 80/443.

## 8. Operations

- **Backups:** use the encrypted R2 backup tooling in Section 10. A volume
  snapshot alone is not an off-host backup.
- **Labeled-data export:** the worker writes a nightly confirmed-mapping corpus
  to `backend/data/exports/labeled/`; pull it live from `GET /api/v1/export/labeled`.
- **Logs:** `docker compose logs -f api worker`. Set `SENTRY_DSN` for error tracking.
- **Upgrades:** `git pull && docker compose up -d --build` (migrations re-run).
- **Scale throughput:** `docker compose up -d --scale worker=N`.

### Application rollback

Use an exact tested Git revision, not a moving branch name. The rollback command
builds that revision, republishes the SPA, recreates API/worker/Caddy, waits for
API and worker health, and performs an authenticated login smoke test. If any
validation fails after switching revisions, it attempts to restore the revision
that was running when the command started.

```bash
git fetch --all --tags --prune
ROLLBACK_DRY_RUN=1 \
ROLLBACK_BASE_URL=https://harmonize.example.org \
ROLLBACK_SMOKE_EMAIL=rollback-check@example.org \
ROLLBACK_SMOKE_PASSWORD='<temporary-or-dedicated-password>' \
  ./scripts/rollback_revision.sh <previous-tested-commit>
```

Run once with `ROLLBACK_DRY_RUN=1` to verify the target and live migration are
compatible without switching revisions. Remove it to execute the rollback.

The command records the prior revision in `.git/metaharmonizer-previous-revision`
and leaves the repository detached at the rollback revision. Return to normal
deployment with `git switch main && git pull --ff-only`.

Rollback never downgrades PostgreSQL automatically. It proceeds only when the
target revision contains the live Alembic head. If the target predates the live
schema, the command aborts before changing source or containers. For that case:

1. Create and verify an encrypted backup.
2. Review every intervening migration downgrade for data loss.
3. Stop application writes.
4. Run the explicit Alembic downgrade from the newer source revision.
5. Run the application rollback and repeat health, login, and critical workflow checks.

Additive schema changes may be backward-compatible, but the presence check is
deliberately stricter: rollback evidence must establish compatibility rather
than infer it. Never use `git reset --hard`, delete persistent volumes, or
restore a production database merely to roll back application code.

## 9. Encrypted PostgreSQL backups to S3-compatible storage

Backups use a dedicated S3-compatible bucket and credentials, separate from
application object storage. Cloudflare R2 is the current target, but AWS S3,
MinIO, and compatible institutional storage use the same endpoint/bucket/key
interface. Dumps are encrypted on the host with AES-256-GCM before upload. The
default retention policy keeps the newest 7 daily, 4 weekly, and 12 monthly
restore points.

Generate the host-only encryption key once:

```bash
mkdir -p ~/.config/metaharmonizer
docker compose run --rm \
  -v "$HOME/.config/metaharmonizer:/keys" \
  api python -m scripts.backup_postgres keygen --key-file /keys/backup.key
chmod 600 ~/.config/metaharmonizer/backup.key
```

Put `BACKUP_R2_ENDPOINT`, `BACKUP_R2_BUCKET`,
`BACKUP_R2_ACCESS_KEY_ID`, and `BACKUP_R2_SECRET_ACCESS_KEY` in the production
`.env`. Run and verify one backup manually before enabling the timer:

```bash
docker compose run --rm \
  -v "$HOME/.config/metaharmonizer/backup.key:/run/secrets/metaharmonizer-backup.key:ro" \
  api python -m scripts.backup_postgres backup
```

Schedule the same one-shot backup command with the host's scheduler only after
the manual backup and clean restore drill succeed. The repository provides an
optional systemd adapter for Linux VMs; adjust `User`, `WorkingDirectory`, and
the key-file host path before installation:

```bash
sudo cp deploy/systemd/metaharmonizer-backup.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now metaharmonizer-backup.timer
systemctl list-timers metaharmonizer-backup.timer
```

Restore into a newly created, non-production database first:

```bash
docker compose exec postgres createdb -U "$POSTGRES_USER" metaharmonizer_restore_test
docker compose run --rm \
  -v "$HOME/.config/metaharmonizer/backup.key:/run/secrets/metaharmonizer-backup.key:ro" \
  api python -m scripts.backup_postgres restore \
    --target-database-url "postgresql+asyncpg://mh:<password>@postgres:5432/metaharmonizer_restore_test"
```

Then point a temporary API container at that database and run `/healthz` plus
the production audit. Never use `--allow-production` during a restore drill.

For Kubernetes, Nomad, or a managed scheduler, run the same Compose/API command
as a scheduled job and mount the encryption key from that platform's secret
store. The backup format and restore CLI are platform-independent.

## 10. cBioPortal validation gate

Before loading a study into cBioPortal, the export runs the LinkML vocabulary
gate. To also run cBioPortal's own `validateData.py`, point the integration test
at it: `CBIO_VALIDATE_DATA=/path/to/validateData.py pytest backend/tests/integration/test_validate_data_gate.py`.
