<#
.SYNOPSIS
  Add the gap-filling cards to the existing MetaHarmonizer SA3.1 Trello board.
.DESCRIPTION
  Fills the gaps found in the plan/requirements review: dev infra, deployment + self-host
  kit (U15), engine-adapter ontology wiring (F-11/F-12), frontend integration (U1/U2 + upload
  guardrails), and spec-v2 cleanup. Reads $env:TRELLO_KEY / $env:TRELLO_TOKEN.
#>
$ErrorActionPreference = "Stop"
$key = $env:TRELLO_KEY; $token = $env:TRELLO_TOKEN
if (-not $key -or -not $token) { throw "Set `$env:TRELLO_KEY and `$env:TRELLO_TOKEN first." }
$base = "https://api.trello.com/1"
function Esc($s) { [uri]::EscapeDataString($s) }
function T-Get($path) { Invoke-RestMethod "$base/$path`?key=$key&token=$token" }
function T-Post($path, $params) { $qs = ($params.GetEnumerator() | % { "$($_.Key)=$(Esc([string]$_.Value))" }) -join "&"; Invoke-RestMethod -Method Post -Uri "$base/$path`?$qs&key=$key&token=$token" }

# locate the board
$boards = T-Get "members/me/boards"
$board = $boards | Where-Object { $_.name -eq "MetaHarmonizer SA3.1" } | Select-Object -First 1
if (-not $board) { throw "Board 'MetaHarmonizer SA3.1' not found." }
$bid = $board.id
Write-Host "Board: $($board.url)" -ForegroundColor Green

# map lists + labels by name
$lists = @{}; (T-Get "boards/$bid/lists") | ForEach-Object { $lists[$_.name] = $_.id }
$labels = @{}; (T-Get "boards/$bid/labels") | ForEach-Object { if ($_.name) { $labels[$_.name] = $_.id } }
$backlog = $lists["Backlog"]

$cards = @()
$cards += @{ phase = "Phase A"; title = "Dev infra — local docker-compose stack";
  goal = "A one-command local stack so every backend sprint has Postgres + Redis + API + worker to build against.";
  acc = "docker compose up brings up Postgres + Redis + FastAPI + arq worker; app boots; healthz green locally.";
  trace = "enables Sprint 2+";
  tasks = @(
    "docker-compose.yml: Postgres + Redis + api + worker (+ Caddy stub)",
    "Dev .env.example with the full env-var catalogue",
    "METAHARMONIZER_DATA_DIR mounted; schema/value dicts in place",
    "Makefile/justfile shortcuts (up/down/migrate/test)",
    "Local healthz/readyz reachable"
  )
}
$cards += @{ phase = "Phase B"; title = "Engine-adapter ontology wiring (F-11) + FieldSuggester panel (F-12)";
  goal = "Route value->ontology resolution through engine_adapter.map_values() -> OntoMapEngine; retire the dashboard-side static NCIT fallback; surface FieldSuggester read-only.";
  acc = "map_values() returns NCIt/EFO/UBERON candidates via the engine; _STATIC_NCIT + nci_cache.json + ONTOLOGY_MAP removed; suggester panel lists unmapped-column field suggestions.";
  trace = "F-11, F-12, U5";
  tasks = @(
    "Implement adapter.map_values() wrapping OntoMapEngine(category, query, ...).run()",
    "Verify ontology output columns from source; normalize to our DTOs",
    "Retire _STATIC_NCIT + nci_cache.json + ONTOLOGY_MAP fallback chain",
    "Provision UMLS_API_KEY for first-run KB build (hosted)",
    "pre_warm() hook wired so first call isn't cold",
    "FieldSuggester read-only panel (suggest_from_schema_mapper output)"
  )
}
$cards += @{ phase = "Phase A"; title = "Frontend integration — wire prototype pages to the real backend";
  goal = "Connect the existing React pages (Upload/MappingReview/Ontology/Quality/Export) to the real persistence + auth + API, replacing prototype/mock data (U1/U2).";
  acc = "Upload -> harmonize -> review -> export round-trip runs against the real backend with a logged-in user; no mock data paths remain.";
  trace = "U1, U2";
  tasks = @(
    "Typed API client against the /api/v1 surface + auth headers",
    "Wire Upload + MappingReview + Ontology + Quality + Export pages to live endpoints",
    "Auth-gated routing + RBAC-aware hiding (viewer cannot mutate)",
    "Upload guardrails: file/type/size validation + Excel gene-symbol warning (SEPT2 -> 2-Sep)",
    "Replace prototype/local state with react-query server state"
  )
}
$cards += @{ phase = "Phase D"; title = "Deployment & self-host kit (U15) + first live deploy";
  goal = "Stand up the hosted stack and ship a clean self-host path: Caddy+TLS, Postgres/Redis containers, R2, domain, KB snapshot pre-build + R2 restore, Kamal deploy.";
  acc = "git clone && cp .env.example .env && docker compose up brings a working instance in <30 min; hosted instance live on its URL with KB restored from R2 (not built on the VM).";
  trace = "U15";
  tasks = @(
    "Caddy reverse proxy + auto Let's Encrypt TLS + HSTS",
    "Kamal deploy config (zero-downtime image swap + one-line rollback)",
    "KB pre-built offline -> snapshot ~/.metaharmonizer/ -> R2; restore at deploy by snapshot id",
    "R2 bucket + domain + Resend + Sentry accounts wired",
    "Self-host docker-compose + .env.example + AUTH_MODE=none path",
    "First live deploy on the hosted URL; smoke test green"
  )
}
$cards += @{ phase = "Phase A"; title = "Spec v2 cleanup + scope finalize";
  goal = "Fold the confirmed scope decisions into the spec so docs match the settled plan (the surviving piece of the old Sprint 1).";
  acc = "Spec reflects all confirmed decisions; no stale open-question wording remains.";
  trace = "";
  tasks = @(
    "Absorb confirmed decisions (active-learning scope, FAISS tuples, ownership, export gate, engine-bundle versioning)",
    "Remove resolved open-question wording",
    "Confirm Web-UI scope items are reflected"
  )
}
$cards += @{ phase = "Phase A"; title = "cBioPortal curation-team follow-ups (Sehyun<->Ritika Slack)";
  goal = "Track the open items surfaced in the Sehyun<->Ritika (cBioPortal curation team) Slack thread so they are not forgotten: keep the data dictionary open/extensible, decide which extra attributes are ontology-backed, and track the experimental attribute-suggester.";
  acc = "Each item has an owner + answer: (a) schema stays open via G6/U9; (b) curators confirm which fields use which ontology before FIELD_ONTOLOGY is extended; (c) attribute-suggester tracked as experimental, built only if curators ask.";
  trace = "G6, U9, U5, F-11, F-12";
  tasks = @(
    "(a) Treat cbioportal_data_dictionary.csv as a SUBSET, not closed (Ritika); keep schema open via G6 diff + U9 admin upload",
    "(b) Get curators' answer: which allowedvalues enums / free-text fields use which ontology (e.g. PRIMARY_SITE -> UBERON; recurrence|...|primary -> ontology terms) BEFORE extending FIELD_ONTOLOGY",
    "(b) Note constraint: ontologies beyond NCIt/UBERON/OncoTree (EFO, HANCESTRO) are engine deps (registry root / new category), not app config",
    "Confirm survival elements OS_*/PFS/DFS in-scope (already in plan section 1.5)",
    "(c) Track experimental 'suggest new attributes' module (FieldSuggester F-12) - build only if curators ask"
  )
}
$cards += @{ phase = "Phase A"; title = "Sehyun app-capability follow-ups (target schema, mapper modes, public deploy)";
  goal = "Track Sehyun's 2026-06 follow-up questions about app capabilities, with grounded status so each is answered or scheduled rather than forgotten.";
  acc = "Each question has a status: built / partial / new feature / env-only. Mapper-mode toggle + column-scoped ontology run scoped as new features; SchemaRegistry alias delivery confirmed as an engine-contract item; public-facing deploy profile documented.";
  trace = "U5, U9, G6, U15, F-11, F-12";
  tasks = @(
    "(1) Target-schema selection: partial (admin upload + schema_versions + active CURATED_PATH); add per-upload user choice of registered schema (folds into U9/G6)",
    "(2)/(3) SchemaRegistry 'schema + alias' delivery: app curated_df has columns only; alias dict is engine-side (schema_mapper FIELD_MODEL). Delivering aliases via upload = NEW engine-contract item - confirm with engine team",
    "(4) Alias-generation tool for user's own schema: agree it lives OUTSIDE the app; app consumes its output",
    "(5) Show context for term selection in Mapping Review (linked columns/row values to disambiguate) - UI enhancement, new",
    "(6) Run-mode toggle SchemaMapper-only / OntologyMapper-only / both: NEW - add mode param to harmonize request; _run_pipeline currently always runs both in sequence",
    "(7) Run OntologyMapper on specified column(s) only: overlaps U5; OntoMapEngine supports per-column scoping; add column-scoped request path + UI",
    "(8) Two deployments (cBioPortal + public) w/ input-size cap: already supported via env (MAX_UPLOAD_MB default 50 + AUTH_MODE=none + anon rate limits); document as deploy profile (U15). Confirm if public also needs a row-count cap"
  )
}

Write-Host "Adding $($cards.Count) gap-filling cards..." -ForegroundColor Cyan
$n = 0
foreach ($c in $cards) {
  $desc = "## Goal`n$($c.goal)`n`n## Acceptance`n$($c.acc)"
  if ($c.trace) { $desc += "`n`n**Traceability:** $($c.trace)" }
  $idLabels = $labels[$c.phase]
  $card = T-Post "cards" @{ idList = $backlog; name = $c.title; desc = $desc; idLabels = $idLabels }
  $chk = T-Post "checklists" @{ idCard = $card.id; name = "Tasks" }
  foreach ($t in $c.tasks) { T-Post "checklists/$($chk.id)/checkItems" @{ name = $t } | Out-Null }
  $n++; Write-Host "  [$n/$($cards.Count)] $($c.title)" -ForegroundColor DarkGray
}
Write-Host "`nDone. Board: $($board.url)" -ForegroundColor Green
