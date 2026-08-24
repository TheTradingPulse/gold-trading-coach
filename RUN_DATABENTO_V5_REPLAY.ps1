$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Python environment not found: $Python" }

Write-Host "Trading Pulse Databento V5 Native Replay" -ForegroundColor Cyan
Write-Host "This writes only to research_data\v5\replay; the dashboard and V4 remain untouched." -ForegroundColor DarkGray

& $Python ".\tools\run_databento_v5_replay.py" --root $PSScriptRoot
if ($LASTEXITCODE -ne 0) { throw "V5 replay failed with exit code $LASTEXITCODE" }

$Report = Join-Path $PSScriptRoot "research_data\v5\replay\databento_v5_replay_report.json"
$Package = Join-Path $env:USERPROFILE "Downloads\TradingPulse_V5_Replay_Result_20260823.zip"
if (-not (Test-Path $Report)) { throw "Replay report was not created" }
Compress-Archive -LiteralPath $Report -DestinationPath $Package -Force
Write-Host "RESULT ZIP READY: $Package" -ForegroundColor Green
