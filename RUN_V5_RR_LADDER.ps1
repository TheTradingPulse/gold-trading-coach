$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Python environment not found: $Python" }
Write-Host "Trading Pulse V5 Point-in-Time R:R Ladder" -ForegroundColor Cyan
Write-Host "Testing verified target-first outcomes from 1R through 20R." -ForegroundColor White
Write-Host "Corrected replay, warehouse, V4 data, and dashboard are read-only." -ForegroundColor DarkGray
& $Python ".\tools\run_v5_rr_ladder.py" --root $PSScriptRoot
if ($LASTEXITCODE -ne 0) { throw "R:R ladder failed with exit code $LASTEXITCODE" }
$Folder=Join-Path $PSScriptRoot "research_data\v5\rr_ladder"
$Result=Join-Path $env:USERPROFILE "Downloads\TradingPulse_V5_RR_Ladder_Result_20260823.zip"
$Files=@(
  (Join-Path $Folder "v5_rr_ladder_report.json"),
  (Join-Path $Folder "v5_rr_1_to_20_ladder.csv"),
  (Join-Path $Folder "v5_rr_holdout_by_symbol.csv")
)
Compress-Archive -LiteralPath $Files -DestinationPath $Result -Force
Write-Host "RESULT ZIP READY: $Result" -ForegroundColor Green

