param(
  [Parameter(Mandatory = $true)]
  [string]$ResultsDirectory
)

$ErrorActionPreference = 'Stop'
$rows = foreach ($file in Get-ChildItem $ResultsDirectory -Filter '*.json' | Sort-Object Name) {
  $summary = Get-Content $file.FullName -Raw | ConvertFrom-Json
  if (-not $summary.metrics.http_reqs) { continue }
  [pscustomobject]@{
    Run = $file.BaseName
    Requests = $summary.metrics.http_reqs.count
    P95Milliseconds = [math]::Round([double]$summary.metrics.http_req_duration.'p(95)', 1)
    FailureRate = [double]$summary.metrics.http_req_failed.value
    CheckRate = [double]$summary.metrics.checks.value
    Accepted = [int]$summary.metrics.harmonize_accepted.count
    UserBackpressure = [int]$summary.metrics.harmonize_user_backpressure.count
    QueueBackpressure = [int]$summary.metrics.harmonize_queue_backpressure.count
    Unexpected = [int]$summary.metrics.harmonize_unexpected.count
  }
}

$rows | Format-Table -AutoSize