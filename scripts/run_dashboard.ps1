<#
.SYNOPSIS
  Run the MetaHarmonizer dashboard against the REAL engine (pre-warmed) for
  interactive testing — backend on :8099 + frontend on :5174.

.DESCRIPTION
  Brings up the dev DB + Redis (portable, no Docker), provisions + migrates an
  isolated DB, seeds the bootstrap admin, then starts the API (which pre-warms
  the engine on startup so the first harmonize is warm) and the Vite frontend
  pointed at it. Open the printed URL and log in with the admin credentials.

  Try a schema: on the Upload page pick a "Target standard" (GDC / cBioPortal /
  cMD / OmicsMLRepo) and harmonize a CSV (e.g. sehyun-input\source-tables\...).

.EXAMPLE
  ./scripts/run_dashboard.ps1
  ./scripts/run_dashboard.ps1 -BackendPort 8099 -FrontendPort 5174
#>
param(
    [int]$BackendPort = 8099,
    [int]$FrontendPort = 5174,
    [string]$Db = "metaharmonizer_e2e",
    [string]$AdminEmail = "admin@example.com",
    [string]$AdminPassword = "DemoPortal2026!"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$py = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "backend venv not found at $py — create it and pip install -r backend/requirements.txt first." }

Write-Host "==> Ensuring dev Postgres (:5433) + Redis (:6380) are up..." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "dev_services.ps1") start | Out-Host

# ---- Real-engine environment (offline, pre-warmed) --------------------------
$env:ENGINE_IMPL = "metaharmonizer"
$env:ONTOLOGY_ENGINE = "1"
$env:JOB_MODE = "inline"
$env:KNOWLEDGE_DB_DIR = (Join-Path $backend "kb_build")
$env:METAHARMONIZER_DATA_DIR = (Join-Path $backend "data")
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
$env:ALLOWED_EMAIL_DOMAINS = ($AdminEmail.Split("@")[-1])
$env:DATABASE_URL = "postgresql+asyncpg://mh:mh_dev_password@127.0.0.1:5433/$Db"
$env:REDIS_URL = "redis://127.0.0.1:6380/3"
if (-not $env:JWT_SECRET) { $env:JWT_SECRET = "dev-secret-key-at-least-32-bytes-long-please" }

Push-Location $backend
try {
    Write-Host "==> Provisioning + migrating DB '$Db'..." -ForegroundColor Cyan
    & $py -m scripts.ensure_db $Db | Out-Host
    & $py -m alembic upgrade head | Out-Host
    Write-Host "==> Seeding admin ($AdminEmail)..." -ForegroundColor Cyan
    & $py -m scripts.seed_account --email $AdminEmail --password $AdminPassword --role admin 2>&1 | Out-Host

    Write-Host "==> Starting backend (pre-warming engine) on :$BackendPort ..." -ForegroundColor Green
    Start-Process -FilePath $py -WorkingDirectory $backend `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$BackendPort")
}
finally { Pop-Location }

# ---- Frontend (Vite) --------------------------------------------------------
$env:VITE_API_TARGET = "http://127.0.0.1:$BackendPort"
Write-Host "==> Starting frontend on :$FrontendPort ..." -ForegroundColor Green
Start-Process -FilePath "cmd.exe" -WorkingDirectory $frontend `
    -ArgumentList @("/c", "npm", "run", "dev", "--", "--port", "$FrontendPort")

Start-Sleep -Seconds 3
Write-Host ""
Write-Host "  Dashboard:  http://127.0.0.1:$FrontendPort" -ForegroundColor Yellow
Write-Host "  Login:      $AdminEmail / $AdminPassword"
Write-Host "  Backend:    http://127.0.0.1:$BackendPort/health  (engine pre-warms in the background)"
Write-Host "  Try:        Upload page -> pick a Target standard -> harmonize a source-table CSV"
