$ErrorActionPreference = "Stop"
Set-Location C:\TradingPulse

Write-Host "Trading Pulse Canonical Consolidation - Phase 2" -ForegroundColor Cyan
Write-Host "Unified contracts and read-only V6 parity audit." -ForegroundColor DarkGray

$python = "C:\TradingPulse\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Python environment not found: $python" }

& $python "C:\TradingPulse\tools\run_canonical_phase2_audit.py"
if ($LASTEXITCODE -ne 0) { throw "Phase 2 audit failed with exit code $LASTEXITCODE" }

& $python "C:\TradingPulse\tests\test_canonical_contracts.py" -v
if ($LASTEXITCODE -ne 0) { throw "Canonical contract tests failed" }

Write-Host "PHASE 2 COMPLETE" -ForegroundColor Green
