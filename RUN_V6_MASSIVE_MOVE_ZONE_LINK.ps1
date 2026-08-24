$ErrorActionPreference = "Stop"
Set-Location C:\TradingPulse

Write-Host "Trading Pulse V6 Massive-Move / Professional-Zone Link" -ForegroundColor Cyan
Write-Host "Read-only analysis. Existing databases and dashboard are untouched." -ForegroundColor DarkGray

$python = "C:\TradingPulse\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Python environment not found: $python" }

& $python "C:\TradingPulse\tools\v6_massive_move_zone_link.py"
if ($LASTEXITCODE -ne 0) { throw "Zone-link analysis failed with exit code $LASTEXITCODE" }

Write-Host "ZONE-LINK ANALYSIS COMPLETE" -ForegroundColor Green
