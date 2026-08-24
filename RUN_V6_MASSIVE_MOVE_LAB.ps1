$ErrorActionPreference = "Stop"
Set-Location C:\TradingPulse

Write-Host "Trading Pulse V6 Massive-Move Discovery Lab" -ForegroundColor Cyan
Write-Host "Research only. Dashboard, V4, V5, and existing V6 results are untouched." -ForegroundColor DarkGray

$python = "C:\TradingPulse\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Python environment not found: $python" }

& $python "C:\TradingPulse\tools\v6_massive_move_lab.py"
if ($LASTEXITCODE -ne 0) { throw "Massive-move lab failed with exit code $LASTEXITCODE" }

Write-Host "MASSIVE-MOVE LAB COMPLETE" -ForegroundColor Green
