# Running MetaHarmonizer locally

A step-by-step guide to run the whole app on your own machine —
**Windows, macOS, or Linux**. Two ways:

- **A. Docker** — one command, works the same on every OS. *Recommended.*
- **B. Native** — run the API + SPA directly (no Docker), for development.

You can also **skip login entirely** for a quick look (see [Skip authentication](#skip-authentication)).

> **TL;DR — fastest possible demo (no ML models, no login):**
> install Docker, then in the repo:
> ```bash
> cp .env.example .env          # Windows: copy .env.example .env
> # edit .env → set:  ENGINE_IMPL=mock   and   AUTH_MODE=none
> docker compose up --build
> ```
> Open **http://localhost:8080** — you're in, no sign-in, with synthetic demo mappings.

---

## What you need

| | Docker path (A) | Native path (B) |
|---|---|---|
| Docker | Docker Desktop (Win/Mac) or Docker Engine + Compose (Linux) | only for Postgres/Redis (optional) |
| Python | — (in the image) | 3.12+ |
| Node | — (in the image) | 20+ |
| Postgres / Redis | — (in the stack) | 16 / 7 (native, or via Docker) |
| Disk / RAM | ~2 GB for the demo; ~15 GB + 8 GB RAM for the **real engine** | same |

The **real ML engine** (NCIt/UBERON ontology mapping) additionally needs a one-time
knowledge-base + models bundle — see [Engine modes](#engine-modes). The **mock**
engine needs none of that and is perfect for trying the UI and workflow.

---

## A. Docker (all platforms)

1. **Install Docker**
   - Windows / macOS: [Docker Desktop](https://www.docker.com/products/docker-desktop/).
   - Ubuntu/Debian: `sudo apt install docker.io docker-compose-plugin` (or Docker's official repo).

2. **Get the code + config**
   ```bash
   git clone https://github.com/AhmedOsamaAli/metaHarmonizer.git
   cd metaHarmonizer
   cp .env.example .env          # Windows PowerShell: copy .env.example .env
   ```

3. **Pick a mode in `.env`** (see the [matrix](#which-config-for-what)). For the
   no-setup demo:
   ```ini
   ENGINE_IMPL=mock
   AUTH_MODE=none
   ```

4. **Start the stack**
   ```bash
   docker compose up --build
   ```
   This brings up Postgres, Redis, the API, the worker, the built SPA, and Caddy.

5. **Open the app** → **http://localhost:8080**
   - With `AUTH_MODE=none` you're dropped straight in as a local admin.
   - With normal auth, create the first admin: `docker compose --profile seed run --rm seed`
     (defaults to `admin@example.com` / `ChangeMe!2026` — override with `SEED_EMAIL` / `SEED_PASSWORD`).

6. **Stop:** `docker compose down` (add `-v` to also wipe the database/volumes).

---

## B. Native (no Docker)

### 1. Install the prerequisites

**Windows**
- [Python 3.12](https://www.python.org/downloads/) and [Node 20](https://nodejs.org/).
- Postgres + Redis: easiest via Docker (`docker compose up -d postgres redis`) or the bundled
  helper `scripts/dev_services.ps1 start`.
- A one-shot dev launcher exists: **`./scripts/run_dashboard.ps1`** (starts DB+Redis, migrates,
  seeds an admin, runs API + Vite).

**macOS**
```bash
brew install python@3.12 node
brew install postgresql@16 redis && brew services start postgresql@16 && brew services start redis
# ...or just run Postgres/Redis via Docker: docker compose up -d postgres redis
```

**Ubuntu / Debian**
```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv nodejs npm
sudo apt install -y postgresql redis-server        # ...or: docker compose up -d postgres redis
```

### 2. Backend (API + worker)
```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt      # installs the vendored engine wheel too

# minimal local config (demo: mock engine + no login)
export ENGINE_IMPL=mock
export AUTH_MODE=none
export DATABASE_URL="postgresql+asyncpg://mh:mh_dev_password@localhost:5432/metaharmonizer"
export REDIS_URL="redis://localhost:6379/0"
#   Windows PowerShell: use  $env:ENGINE_IMPL="mock"  etc.

alembic upgrade head                 # create the schema
uvicorn app.main:app --port 8000     # API on http://localhost:8000
```

### 3. Frontend (SPA)  — in a second terminal
```bash
cd frontend
npm install
npm run dev                          # Vite dev server, proxies /api to the API
```
Open the URL Vite prints (e.g. http://localhost:5173).

---

## Engine modes

| `ENGINE_IMPL` | What it does | Needs a download? |
|---|---|---|
| `mock` | Deterministic synthetic mappings — great for UI/workflow demos and CI. | **No.** |
| `metaharmonizer` | The real engine: schema mapping + NCIt/UBERON ontology mapping via embeddings + KB. | **Yes** — a one-time offline bundle. |

For the **real engine**, build and seed the knowledge-base + models bundle **once**
(needs internet + a free `UMLS_API_KEY` the first time), then set
`ENGINE_IMPL=metaharmonizer` and `ONTOLOGY_ENGINE=1`. The full recipe (build with
`scripts.package_kb`, seed with `docker compose --profile kb run --rm kb-import`) is in
**[DEPLOY.md](DEPLOY.md)**.

---

## Skip authentication

For a local look you don't have to register or verify an email — set **`AUTH_MODE=none`**.

- The **API** then treats every request as a local admin (no tokens needed).
- The **SPA** detects the open API on load and drops you straight into the dashboard —
  no login screen.
- `JWT_SECRET` is not required in this mode.

> ⚠️ **Local/dev only.** Never deploy with `AUTH_MODE=none` — it disables all access
> control. For anything shared, use `AUTH_MODE=jwt` (the default) and seed an admin.

With normal auth (`AUTH_MODE=jwt`): the **first** account to register becomes the admin
(auto-verified); trusted-domain signups (`ALLOWED_EMAIL_DOMAINS`) are active immediately,
everyone else is a curator pending an admin's approval.

---

## Which config for what

| Goal | `ENGINE_IMPL` | `AUTH_MODE` | KB download? | Email setup? |
|---|---|---|---|---|
| Try the UI / workflow | `mock` | `none` | no | no |
| Real mappings, no login | `metaharmonizer` | `none` | **yes** | no |
| Production-like | `metaharmonizer` | `jwt` | **yes** | for verification |

---

## Troubleshooting

- **Port already in use (8080 / 8000 / 5432 / 6379):** stop the other service, or change the
  published ports in `docker-compose.override.yml`.
- **Ontology mapping returns only dictionary hits:** the KB isn't seeded — either seed it
  (see DEPLOY.md) or use `ENGINE_IMPL=mock` for the demo.
- **`JWT_SECRET must be at least 32 bytes`:** you're in `AUTH_MODE=jwt` — set a long
  `JWT_SECRET` in `.env`, or use `AUTH_MODE=none` for local use.
- **Fresh clone is missing the KB / models:** that's expected — they're large and built
  out-of-band (see [Engine modes](#engine-modes)); the `mock` engine needs none of them.
- **Reset everything (Docker):** `docker compose down -v` wipes the database and caches.
