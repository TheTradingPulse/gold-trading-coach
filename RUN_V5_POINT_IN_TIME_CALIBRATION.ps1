$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Python environment not found: $Python" }
Write-Host "Trading Pulse V5 Corrected Point-in-Time Calibration" -ForegroundColor Cyan
Write-Host "2021-2023 development, 2024 calibration, 2025 untouched holdout." -ForegroundColor White
Write-Host "Dashboard, warehouse, replay databases, V4, and R:R results are read-only." -ForegroundColor DarkGray
& $Python ".\tools\run_v5_point_in_time_calibration.py" --root $PSScriptRoot
if ($LASTEXITCODE -ne 0) { throw "Corrected calibration failed with exit code $LASTEXITCODE" }
$Folder=Join-Path $PSScriptRoot "research_data\v5\calibration_point_in_time"
$Result=Join-Path $env:USERPROFILE "Downloads\TradingPulse_V5_Point_In_Time_Calibration_Result_20260823.zip"
$Files=Get-ChildItem $Folder -File | Where-Object { $_.Name -like "*.json" -or $_.Name -like "audit_*.csv" -or $_.Name -eq "top_preselected_rules_with_holdout.csv" }
Compress-Archive -LiteralPath $Files.FullName -DestinationPath $Result -Force
Write-Host "RESULT ZIP READY: $Result" -ForegroundColor Green

