$ErrorActionPreference = "Stop"
Set-Location C:\TradingPulse

Write-Host "Trading Pulse Canonical Phase 3B - Live Shadow Snapshot" -ForegroundColor Cyan
Write-Host "Yahoo reference data only. No live promotion or dashboard changes." -ForegroundColor DarkGray

$python = "C:\TradingPulse\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Python environment not found: $python" }

& $python "C:\TradingPulse\tools\run_canonical_live_shadow.py"
if ($LASTEXITCODE -ne 0) { throw "Live shadow snapshot failed with exit code $LASTEXITCODE" }

Write-Host "PHASE 3B COMPLETE" -ForegroundColor Green
