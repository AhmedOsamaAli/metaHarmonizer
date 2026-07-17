# Running MetaHarmonizer locally

**One path, five steps, the same on Windows, macOS, and Linux — Docker.**

You don't edit any configuration to get running: `.env.example` ships preconfigured
(a dev login secret and the public knowledge-base download URL are already set).
MetaHarmonizer always runs the real ML engine, so the only sizeable step is a
**one-time ~1.4 GB download** of the engine knowledge base + embedding models.

## Prerequisites

- **Docker** — [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/macOS) or Docker Engine + Compose plugin (Linux).
- **~15 GB free disk** and **~8 GB RAM** (models + knowledge base + Postgres).

## Setup

```bash
# 1 — Get the code
git clone https://github.com/AhmedOsamaAli/metaHarmonizer.git
cd metaHarmonizer

# 2 — Create your .env (boots as-is — dev secret + KB download URL are preset)
cp .env.example .env                              # Windows PowerShell:  copy .env.example .env

# 3 — Download + install the engine knowledge base & models (~1.4 GB, one-time)
docker compose --profile kb run --rm kb-import

# 4 — Build and start the whole stack
docker compose up --build

# 5 — Open the app  →  http://localhost:8080
```

On first open, **register an account — the *first* account on an empty database becomes
the admin** (auto-verified, ready to sign in immediately). Later accounts are curators
who must confirm their email — and because a local install sends no email, **only that
first account can sign in** unless you configure a mail provider.

**Just trying it out? Skip login entirely** — set `AUTH_MODE=none` in `.env` before step 4
(see Optional below). You're dropped straight into the dashboard as an admin — no
registration, email, or approval — and it works even if the database already has
accounts. This is the smoothest path for evaluation.

**Prefer a ready-made login** (e.g. to hand to a teammate)? Instead of registering,
seed one — run from the project root (the folder with `docker-compose.yml`):

```bash
docker compose --profile seed run --rm seed
```

Creates `admin@example.com` / `ChangeMe!2026` (admin, verified). Override with
`SEED_EMAIL` / `SEED_PASSWORD`. It's idempotent — an existing account is left unchanged
(it won't reset the password), so run it on a fresh database or use a new email.

To stop: `docker compose down` (add `-v` to also wipe the database and caches).

## Verify it's working

- **App:** <http://localhost:8080>
- **API health:** <http://localhost:8000/healthz> → `{"status":"ok"}`
- **API docs (OpenAPI):** <http://localhost:8000/docs>

Upload a CSV/TSV of clinical metadata and click **Run harmonization**. Progress
streams in the jobs tray (bottom-right); when it finishes, open **Review** to
accept or correct the mappings.

---

## Optional (one line each in `.env`, before step 4)

- **Skip login (recommended for evaluation)** — set `AUTH_MODE=none` to be dropped
  straight into the dashboard as a local admin, with no registration, email, or approval.
  Set it before step 4 and it just works; change it later and re-run
  `docker compose up -d --force-recreate api` for it to take effect. **Local use only** —
  never deploy with it.
- **Best ontology matches (Stage-4 LLM)** — set `GEMINI_API_KEY=your-key` to enable
  the LLM fallback for the hardest columns. Without it, the earlier stages still run.

## Troubleshooting

- **Registered an account but can't sign in** — only the *first* account on an empty
  database is auto-verified. Later self-registrations must confirm their email, which a
  local install can't send, so sign-in is blocked ("verify your email" / "awaiting
  approval"). Easiest fix: set `AUTH_MODE=none` (skip login), then
  `docker compose up -d --force-recreate api`. Or reset with `docker compose down -v` and
  register once, or seed an account.
- **Credentials from someone else don't work** — accounts live in the database and don't
  transfer between machines/installs; each install needs its own first account (or seed).
- **Ontology mapping returns no NCIt / UBERON codes** — the KB step didn't complete.
  Re-run `docker compose --profile kb run --rm kb-import` and confirm it prints a
  `downloaded … MiB` line.
- **Port already in use (8080 / 8000 / 5432 / 6379)** — stop the conflicting service,
  or change the published port in `docker-compose.override.yml`.
- **`JWT_SECRET must be at least 32 bytes`** — only happens on a native run (below)
  with `AUTH_MODE=jwt`; set `AUTH_MODE=none` in `backend/.env` for local dev, or
  supply a real `JWT_SECRET`.
- **Reset everything** — `docker compose down -v` wipes the database and all caches
  (you'll re-run step 3).

---

## Develop natively (contributors)

Prefer hot reload without rebuilding images? Keep Postgres + Redis in Docker and run
the API and SPA on the host. Requires **Python 3.12+** and **Node 20+**.

```bash
# Datastores only
docker compose up -d postgres redis

# Backend — terminal 1
cd backend
cp ../.env.example .env          # the backend loads ./.env; its localhost DSNs match the services above
#   then set AUTH_MODE=none in backend/.env for local dev (or a real JWT_SECRET)
python3.12 -m venv .venv
source .venv/bin/activate         # Windows PowerShell:  .venv\Scripts\Activate.ps1
pip install -r requirements.txt   # installs the vendored engine wheel + torch
python -m scripts.seed_kb ../kb/kb_offline_bundle.tar.gz   # one-time; downloads the bundle if absent
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Frontend — terminal 2
cd frontend
npm install
npm run dev                       # Vite dev server, proxies /api to :8000
```

Open the URL Vite prints (e.g. <http://localhost:5173>).
Building or upgrading the KB bundle itself is covered in **[DEPLOY.md](DEPLOY.md)**.

