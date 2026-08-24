$ErrorActionPreference="Stop"
Set-Location $PSScriptRoot
$Python=Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if(-not(Test-Path $Python)){throw "Python environment not found: $Python"}
Write-Host "Trading Pulse V5 Professional Point-in-Time Feature Lab" -ForegroundColor Cyan
Write-Host "Enriching corrected trades with structure, regime, curve, volume, room, and session context." -ForegroundColor White
Write-Host "All existing databases, raw data, dashboard, and grading logic remain read-only." -ForegroundColor DarkGray
& $Python ".\tools\run_v5_professional_feature_lab.py" --root $PSScriptRoot
if($LASTEXITCODE -ne 0){throw "Professional feature lab failed with exit code $LASTEXITCODE"}
$Folder=Join-Path $PSScriptRoot "research_data\v5\professional_feature_lab"
$Result=Join-Path $env:USERPROFILE "Downloads\TradingPulse_V5_Professional_Feature_Lab_Result_20260823.zip"
$Files=Get-ChildItem $Folder -File|Where-Object{$_.Name -like "*.json" -or $_.Name -like "*.csv"}
Compress-Archive -LiteralPath $Files.FullName -DestinationPath $Result -Force
Write-Host "RESULT ZIP READY: $Result" -ForegroundColor Green

