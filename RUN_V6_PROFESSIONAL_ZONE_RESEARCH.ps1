$ErrorActionPreference="Stop"
Set-Location $PSScriptRoot
$Python=Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if(-not(Test-Path $Python)){throw "Python environment not found: $Python"}
Write-Host "Trading Pulse V6 Professional Zone Research" -ForegroundColor Cyan
Write-Host "OTA-style 5m zones, 15m trend, 1H curve, first retests, and 1R-20R evidence." -ForegroundColor White
Write-Host "Checkpointed by symbol. Dashboard, V4, V5, and installed reference library are untouched." -ForegroundColor DarkGray
& $Python ".\tools\run_v6_professional_zone_research.py" --root $PSScriptRoot
if($LASTEXITCODE -ne 0){throw "V6 research failed with exit code $LASTEXITCODE"}
$Folder=Join-Path $PSScriptRoot "research_data\v6"
$Result=Join-Path $env:USERPROFILE "Downloads\TradingPulse_V6_Professional_Zone_Result_20260823.zip"
$Files=@((Join-Path $Folder "v6_professional_zone_report.json"),(Join-Path $Folder "v6_score_rr_ladder.csv"))
Compress-Archive -LiteralPath $Files -DestinationPath $Result -Force
Write-Host "RESULT ZIP READY: $Result" -ForegroundColor Green

