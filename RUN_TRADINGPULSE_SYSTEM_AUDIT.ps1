$ErrorActionPreference = "Stop"
Set-Location C:\TradingPulse

Write-Host "Trading Pulse Whole-System Architecture Audit" -ForegroundColor Cyan
Write-Host "Read-only inventory. Nothing will be deleted, moved, upgraded, or rewritten." -ForegroundColor DarkGray

$python = "C:\TradingPulse\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Python environment not found: $python" }

& $python "C:\TradingPulse\tools\tradingpulse_system_audit.py"
if ($LASTEXITCODE -ne 0) { throw "System audit failed with exit code $LASTEXITCODE" }

Write-Host "SYSTEM AUDIT COMPLETE" -ForegroundColor Green
