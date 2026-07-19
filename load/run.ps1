<#
.SYNOPSIS
  Run a k6 load profile against a MetaHarmonizer instance.

.DESCRIPTION
  Thin wrapper around `k6 run` that passes the standard env vars. Install k6
  first: `winget install k6 --source winget` (or see https://k6.io/docs/).

.EXAMPLE
  ./load/run.ps1 -Suite smoke
  ./load/run.ps1 -Suite load  -BaseUrl http://localhost:8000 -Vus 50 -Hold 5m
  ./load/run.ps1 -Suite stress -Vus 25
  ./load/run.ps1 -Suite harmonize -Rate 5 -Duration 2m
#>
param(
  [ValidateSet('smoke', 'load', 'stress', 'soak', 'harmonize_submit', 'harmonize')]
  [string]$Suite = 'smoke',
  [string]$BaseUrl = 'http://localhost:8000',
  [string]$Email = 'admin@example.com',
  [string]$Password = 'ChangeMe!2026',
  [int]$Vus = 25,
  [string]$Hold = '2m',
  [int]$Rate = 2,
  [string]$Duration = '1m',
  [string]$Out = ''
)
$ErrorActionPreference = 'Stop'

if (-not (Get-Command k6 -ErrorAction SilentlyContinue)) {
  Write-Error "k6 not found. Install with: winget install k6 --source winget  (or https://k6.io/docs/get-started/installation/)"
  exit 127
}

if ($Suite -eq 'harmonize') { $Suite = 'harmonize_submit' }
$script = Join-Path $PSScriptRoot "k6/$Suite.js"
if (-not (Test-Path $script)) { throw "no such profile: $script" }

$k6Args = @(
  'run', $script,
  '-e', "BASE_URL=$BaseUrl",
  '-e', "EMAIL=$Email",
  '-e', "PASSWORD=$Password",
  '-e', "VUS=$Vus",
  '-e', "HOLD=$Hold",
  '-e', "RATE=$Rate",
  '-e', "DURATION=$Duration"
)
if ($Out) { $k6Args += @('--out', $Out) }

Write-Host "k6 $($k6Args -join ' ')" -ForegroundColor Cyan
& k6 @k6Args
