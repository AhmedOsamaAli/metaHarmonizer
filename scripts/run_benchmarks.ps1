<#
.SYNOPSIS
  Run the MetaHarmonizer evaluation benchmarks on Sehyun's provided datasets.

.DESCRIPTION
  Drives the REAL engine over the provided test sets and prints per-item timings
  + a correctness-oriented summary. Writes CSVs next to backend\ for review.

    schema   : CPTAC source-tables -> GDC   (SchemaMapper)   -> schema_gdc.csv (+ _detail)
    cmd      : AsnicarF            -> cMD    (SchemaMapper)   -> schema_cmd.csv (+ _detail)
    ontology : om_benchmark_*.csv  -> NCIt   (OntologyMapper) -> ontology_run.log

  Engine models load from local caches (offline). First run is cold (~30s load).

.EXAMPLE
  ./scripts/run_benchmarks.ps1                 # everything
  ./scripts/run_benchmarks.ps1 -Suite schema   # just CPTAC -> GDC
  ./scripts/run_benchmarks.ps1 -Suite ontology -Limit 150
#>
param(
    [ValidateSet("all", "schema", "cmd", "ontology")]
    [string]$Suite = "all",
    [int]$Limit = 0   # ontology: max queries per benchmark (0 = all)
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$sehyun = Join-Path $root "sehyun-input"
$py = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "backend venv not found at $py" }

$env:METAHARMONIZER_DATA_DIR = (Join-Path $backend "data")
$env:KNOWLEDGE_DB_DIR = (Join-Path $backend "kb_build")
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
$env:PYTHONUTF8 = "1"

Push-Location $backend
try {
    if ($Suite -in @("all", "schema")) {
        Write-Host "==> SchemaMapper: CPTAC source-tables -> GDC" -ForegroundColor Cyan
        & $py -m scripts.eval_schema --tables (Join-Path $sehyun "source-tables\source-tables") --schema gdc --out schema_gdc.csv
    }
    if ($Suite -in @("all", "cmd")) {
        Write-Host "==> SchemaMapper: AsnicarF -> cMD" -ForegroundColor Cyan
        $td = Join-Path $sehyun "_cmd_tables"; New-Item -ItemType Directory -Force -Path $td | Out-Null
        Import-Csv (Join-Path $sehyun "AsnicarF_2017_metadata.tsv") -Delimiter "`t" |
        Export-Csv (Join-Path $td "AsnicarF_2017.csv") -NoTypeInformation
        $cmd = Join-Path $backend "data\schema\registry\curatedmetagenomicdata\cmd_target_attrs.csv"
        & $py -m scripts.eval_schema --tables $td --target-schema-path $cmd --out schema_cmd.csv
    }
    if ($Suite -in @("all", "ontology")) {
        Write-Host "==> OntologyMapper: EFO benchmarks -> NCIt corpus" -ForegroundColor Cyan
        foreach ($b in "om_benchmark_ols_efo_disease", "om_benchmark_ukbb_efo", "om_benchmark_biomappings_efo", "om_benchmark_ols_efo_full") {
            Write-Host "--- $b ---" -ForegroundColor DarkGray
            & $py -m scripts.eval_ontology --benchmark (Join-Path $sehyun "$b.csv") --category disease --source ncit --limit $Limit
        }
    }
}
finally { Pop-Location }
Write-Host "Done. CSVs written under backend\ (schema_gdc.csv / schema_cmd.csv + *_detail.csv)." -ForegroundColor Green
