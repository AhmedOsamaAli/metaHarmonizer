# Self-hosting MetaHarmonizer

A step-by-step runbook to stand up a production instance with Docker Compose.
Target: a curator team self-hosts on one VM. The stack is **Postgres + Redis +
API + arq worker + Caddy (serving the built SPA)**.

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

| Variable | Set to |
| --- | --- |
| `JWT_SECRET` | a real 32+ byte secret: `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `POSTGRES_PASSWORD` | a strong password |
| `JOB_MODE` | `queue` (so the worker runs harmonizations) |
| `ALLOWED_EMAIL_DOMAINS` | your org's email domain(s), comma-separated |
| `CORS_ORIGINS` / `APP_BASE_URL` | your public URL (e.g. `https://harmonize.example.org`) |
| `HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE` | `1` (load models from the seeded cache) |
| `RESEND_API_KEY` | (optional) for verification / reset emails; without it, links are logged |

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

Edit the `Caddyfile` to your domain; Caddy provisions and renews certificates
automatically. Set `APP_BASE_URL=https://...` and `COOKIE_SECURE=true` in `.env`.

## 8. Operations

- **Backups:** the `pg_data` Docker volume holds all state — snapshot it
  regularly (`docker run --rm -v metaharmonizer_pg_data:/v ... tar`), or use
  `pg_dump`.
- **Labeled-data export:** the worker writes a nightly confirmed-mapping corpus
  to `backend/data/exports/labeled/`; pull it live from `GET /api/v1/export/labeled`.
- **Logs:** `docker compose logs -f api worker`. Set `SENTRY_DSN` for error tracking.
- **Upgrades:** `git pull && docker compose up -d --build` (migrations re-run).
- **Scale throughput:** `docker compose up -d --scale worker=N`.

## 9. cBioPortal validation gate

Before loading a study into cBioPortal, the export runs the LinkML vocabulary
gate. To also run cBioPortal's own `validateData.py`, point the integration test
at it: `CBIO_VALIDATE_DATA=/path/to/validateData.py pytest backend/tests/integration/test_validate_data_gate.py`.
