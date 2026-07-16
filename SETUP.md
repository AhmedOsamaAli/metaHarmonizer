# Running MetaHarmonizer locally

A step-by-step guide to run the app on your own machine — **Windows, macOS, or Linux**.

MetaHarmonizer runs the **real ML engine** everywhere — locally and in production.
There is no "lite" mode: schema columns go through the four-stage cascade
(dictionary → fuzzy → embeddings → optional LLM) and values are resolved to real
NCIt / UBERON codes via the engine's knowledge base. That means a **one-time
knowledge-base + models setup** (below) before the ontology mapping works.

Two ways to run:
- **A. Docker** — one stack, same on every OS. *Recommended.*
- **B. Native** — API + SPA directly, for development.

You can **skip login** for local use (see [Skip authentication](#skip-authentication)).

---

## What you need

| | Docker path (A) | Native path (B) |
|---|---|---|
| Docker | Docker Desktop (Win/Mac) or Engine + Compose (Linux) | only for Postgres/Redis (optional) |
| Python | — (in the image) | 3.12+ |
| Node | — (in the image) | 20+ |
| Postgres / Redis | — (in the stack) | 16 / 7 (native or via Docker) |
| Disk / RAM | **~15 GB disk, ~8 GB RAM** (models + KB + Postgres) | same |
| **Engine KB + models** | **required, one-time** — see [step 2](#2-get-the-engine-kb--models-one-time) | same |

> **Optional but recommended:** a `GEMINI_API_KEY` to enable the **Stage-4 LLM**
> for the hardest columns (see [Stage-4 LLM](#stage-4-llm-optional)).

---

## 1. Get the code

```bash
git clone https://github.com/AhmedOsamaAli/metaHarmonizer.git
cd metaHarmonizer
cp .env.example .env          # Windows PowerShell: copy .env.example .env
```

## 2. Get the engine KB + models (one-time)

The real engine needs a **knowledge base** (FAISS + SQLite indexes over NCIt/UBERON/…)
and **embedding models** (MiniLM for schema, SapBERT for ontology). These are large
(~1.4 GB) and shipped **out-of-band**, not in the repo. Pick one:

**A — Use a prebuilt bundle (recommended for a fresh run).** Get
`kb_offline_bundle.tar.gz` from the maintainer or a published GitHub Release, then either:
- drop it at `./kb/kb_offline_bundle.tar.gz`, **or**
- set `KB_BUNDLE_URL` (+ `KB_BUNDLE_SHA256`) in `.env` so `kb-import` downloads it.

**B — Build it yourself (maintainers).** On a machine with internet + a free
`UMLS_API_KEY` the first time:

```bash
cd backend
python -m scripts.package_kb -o ../kb/kb_offline_bundle.tar.gz   # ~1.4 GB models + KB
```

The full recipe (and how to pin/upgrade it) is in **[DEPLOY.md](DEPLOY.md)**. Either way,
the seed step (below) installs it into the stack; new machines with no bundle **and** no
`KB_BUNDLE_URL` will fail the seed with a clear "bundle not found" message.

---

## A. Docker (all platforms)

1. **Install Docker** — [Docker Desktop](https://www.docker.com/products/docker-desktop/)
   (Win/Mac) or `sudo apt install docker.io docker-compose-plugin` (Ubuntu/Debian).

2. **Configure `.env`** (see the [matrix](#which-config-for-what)):
   ```ini
   ENGINE_IMPL=metaharmonizer
   ONTOLOGY_ENGINE=1
   AUTH_MODE=none          # skip login for local use (omit for real auth)
   # GEMINI_API_KEY=...    # optional — enables the Stage-4 LLM
   ```

3. **Seed the KB + models** into the stack (one-time):
   ```bash
   docker compose --profile kb run --rm kb-import
   ```

4. **Start the stack:**
   ```bash
   docker compose up --build
   ```

5. **Open the app** → **http://localhost:8080**
   - With `AUTH_MODE=none` you're dropped straight in as a local admin.
   - With real auth, create the first admin: `docker compose --profile seed run --rm seed`.

6. **Stop:** `docker compose down` (add `-v` to also wipe the database + caches).

---

## B. Native (no Docker)

### 1. Prerequisites

**Windows** — [Python 3.12](https://www.python.org/downloads/), [Node 20](https://nodejs.org/);
Postgres+Redis via Docker (`docker compose up -d postgres redis`) or `scripts/dev_services.ps1 start`.
A one-shot launcher exists: **`./scripts/run_dashboard.ps1`**.

**macOS**
```bash
brew install python@3.12 node
brew install postgresql@16 redis && brew services start postgresql@16 && brew services start redis
#   ...or just: docker compose up -d postgres redis
```

**Ubuntu / Debian**
```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv nodejs npm
sudo apt install -y postgresql redis-server          # ...or: docker compose up -d postgres redis
```

### 2. Seed the KB + models (one-time)
```bash
cd backend && source .venv/bin/activate   # after the venv exists (next step)
python -m scripts.seed_kb ../kb/kb_offline_bundle.tar.gz
```

### 3. Backend (API)
```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate                 # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt           # installs the vendored engine wheel + torch

export ENGINE_IMPL=metaharmonizer
export ONTOLOGY_ENGINE=1
export AUTH_MODE=none                      # skip login (local only)
export DATABASE_URL="postgresql+asyncpg://mh:mh_dev_password@localhost:5432/metaharmonizer"
export REDIS_URL="redis://localhost:6379/0"
# export GEMINI_API_KEY=...               # optional, enables Stage-4 LLM
#   Windows PowerShell: use  $env:ENGINE_IMPL="metaharmonizer"  etc.

alembic upgrade head
uvicorn app.main:app --port 8000
```

### 4. Frontend (SPA) — second terminal
```bash
cd frontend
npm install
npm run dev                                # Vite dev server, proxies /api to the API
```
Open the URL Vite prints (e.g. http://localhost:5173).

---

## Skip authentication

For a local look you don't have to register or verify email — set **`AUTH_MODE=none`**.

- The **API** treats every request as a local admin (no tokens; `JWT_SECRET` not required).
- The **SPA** detects the open API on load and drops you into the dashboard — no login screen.

> ⚠️ **Local/dev only.** Never deploy with `AUTH_MODE=none` — it disables all access control.
> For anything shared, use `AUTH_MODE=jwt` (the default): the **first** account to register
> becomes the admin; trusted-domain signups (`ALLOWED_EMAIL_DOMAINS`) are active immediately,
> everyone else is a curator pending an admin's approval.

## Stage-4 LLM (optional)

The engine's fourth stage uses an LLM for the hardest columns the earlier stages can't
resolve confidently. It's **off unless you provide a key**:

```ini
GEMINI_API_KEY=your-key       # enables Stage-4 LLM in the pipeline + the per-column "LLM re-match"
```

Without it, schema mapping runs stages 1–3 (dictionary, fuzzy, embeddings) and ontology
mapping runs stages 1–2.5 (exact, SapBERT, synonym boost) — no LLM. Everything else works.

---

## Which config for what

| Goal | `ENGINE_IMPL` | `AUTH_MODE` | `GEMINI_API_KEY` | KB needed |
|---|---|---|---|---|
| Local, no login | `metaharmonizer` | `none` | optional | **yes** |
| Local, real auth | `metaharmonizer` | `jwt` | optional | **yes** |
| Production | `metaharmonizer` | `jwt` | recommended | **yes** |

---

## Troubleshooting

- **Ontology mapping returns only dictionary hits (no NCIt/UBERON codes):** the KB isn't
  seeded — run the seed step ([step 2](#2-get-the-engine-kb--models-one-time)) and make sure
  `ONTOLOGY_ENGINE=1`.
- **Port already in use (8080 / 8000 / 5432 / 6379):** stop the other service or change the
  published ports in `docker-compose.override.yml`.
- **`JWT_SECRET must be at least 32 bytes`:** you're in `AUTH_MODE=jwt` — set a long
  `JWT_SECRET` in `.env`, or use `AUTH_MODE=none` for local use.
- **"LLM re-match" errors / no Stage-4 matches:** `GEMINI_API_KEY` isn't set (see above).
- **Reset everything (Docker):** `docker compose down -v` wipes the database and caches.
