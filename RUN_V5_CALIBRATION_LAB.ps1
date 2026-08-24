$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Python environment not found: $Python" }
Write-Host "Trading Pulse V5 Chronological Calibration Lab" -ForegroundColor Cyan
Write-Host "Read-only evidence analysis. Dashboard and V4/V5 evidence are not modified." -ForegroundColor DarkGray
& $Python ".\tools\run_v5_calibration_lab.py" --root $PSScriptRoot
if ($LASTEXITCODE -ne 0) { throw "Calibration audit failed with exit code $LASTEXITCODE" }
$Folder = Join-Path $PSScriptRoot "research_data\v5\calibration"
$Result = Join-Path $env:USERPROFILE "Downloads\TradingPulse_V5_Calibration_Audit_20260823.zip"
$Files = Get-ChildItem $Folder -File | Where-Object { $_.Name -like "*.json" -or $_.Name -like "audit_*.csv" -or $_.Name -eq "top_preselected_rules_with_holdout.csv" }
Compress-Archive -LiteralPath $Files.FullName -DestinationPath $Result -Force
Write-Host "RESULT ZIP READY: $Result" -ForegroundColor Green
