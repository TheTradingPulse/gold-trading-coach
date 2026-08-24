$ErrorActionPreference = "Stop"
Set-Location C:\TradingPulse

Write-Host "Trading Pulse Canonical Phase 3A - V6 Shadow Parity" -ForegroundColor Cyan
Write-Host "Read-only warehouse/reference comparison. Dashboard remains unchanged." -ForegroundColor DarkGray

$python = "C:\TradingPulse\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Python environment not found: $python" }

& $python "C:\TradingPulse\tools\run_canonical_v6_shadow_parity.py"
if ($LASTEXITCODE -ne 0) { throw "V6 shadow parity failed with exit code $LASTEXITCODE" }

Write-Host "PHASE 3A COMPLETE" -ForegroundColor Green
