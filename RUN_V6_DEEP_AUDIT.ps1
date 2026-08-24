$ErrorActionPreference="Stop"
Set-Location $PSScriptRoot
$Python=Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if(-not(Test-Path $Python)){throw "Python environment not found: $Python"}
Write-Host "Trading Pulse V6 Professional Deep Audit" -ForegroundColor Cyan
Write-Host "Symbol, pattern, direction, session, basing, costs, and leave-one-market-out stability." -ForegroundColor White
& $Python ".\tools\run_v6_deep_audit.py" --root $PSScriptRoot
if($LASTEXITCODE -ne 0){throw "V6 deep audit failed with exit code $LASTEXITCODE"}
$Folder=Join-Path $PSScriptRoot "research_data\v6\deep_audit"
$Result=Join-Path $env:USERPROFILE "Downloads\TradingPulse_V6_Deep_Audit_Result_20260823.zip"
$Files=Get-ChildItem $Folder -File|Where-Object{$_.Name -like "*.json" -or $_.Name -like "*.csv"}
Compress-Archive -LiteralPath $Files.FullName -DestinationPath $Result -Force
Write-Host "RESULT ZIP READY: $Result" -ForegroundColor Green

