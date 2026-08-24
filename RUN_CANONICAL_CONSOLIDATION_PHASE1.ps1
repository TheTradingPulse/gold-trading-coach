$ErrorActionPreference = "Stop"
Set-Location C:\TradingPulse

Write-Host "Trading Pulse Canonical Consolidation - Phase 1" -ForegroundColor Cyan
Write-Host "Recoverable archive only. Dashboard and research data will not be modified." -ForegroundColor DarkGray

$python = "C:\TradingPulse\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Python environment not found: $python" }

& $python "C:\TradingPulse\tools\canonical_consolidation_phase1.py"
if ($LASTEXITCODE -ne 0) { throw "Consolidation failed with exit code $LASTEXITCODE" }

Write-Host "PHASE 1 CONSOLIDATION COMPLETE" -ForegroundColor Green
