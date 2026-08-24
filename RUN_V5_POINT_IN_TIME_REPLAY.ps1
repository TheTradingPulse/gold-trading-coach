$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Python environment not found: $Python" }

Write-Host "Trading Pulse V5 Point-in-Time Replay" -ForegroundColor Cyan
Write-Host "Corrects candle-close timing and higher-timeframe lookahead." -ForegroundColor White
Write-Host "The original replay, warehouse, V4 data, and dashboard are not modified." -ForegroundColor DarkGray

& $Python ".\tools\run_v5_point_in_time_replay_20260823.py" --root $PSScriptRoot
if ($LASTEXITCODE -ne 0) { throw "Point-in-time replay failed with exit code $LASTEXITCODE" }

$Folder = Join-Path $PSScriptRoot "research_data\v5\replay_point_in_time"
$Report = Join-Path $Folder "databento_v5_replay_report.json"
$Package = Join-Path $env:USERPROFILE "Downloads\TradingPulse_V5_Point_In_Time_Replay_Result_20260823.zip"
if (-not (Test-Path $Report)) { throw "Point-in-time replay report was not created" }

Compress-Archive -LiteralPath $Report -DestinationPath $Package -Force
Write-Host "RESULT ZIP READY: $Package" -ForegroundColor Green
