param([switch]$ApproveDownload)
$ErrorActionPreference="Stop";Set-Location $PSScriptRoot
Write-Host "Trading Pulse Phase 3I - Frozen 2026 GC Confirmation" -ForegroundColor Cyan
Write-Host "Original entry + ATR1 stop + 5R. No parameter search." -ForegroundColor DarkGray
$old=$env:PYTHONPATH;$env:PYTHONPATH="${PSScriptRoot};${PSScriptRoot}\core";if($old){$env:PYTHONPATH="$env:PYTHONPATH;$old"}
try{
 & ".\.venv\Scripts\python.exe" -m unittest tests.test_phase3i_frozen -v
 if($LASTEXITCODE -ne 0){throw "Frozen hypothesis tests failed"}
 $args=@("tools\run_phase3i_frozen_gc_confirmation.py");if($ApproveDownload){$args+="--approve-download"}
 & ".\.venv\Scripts\python.exe" @args
 $code=$LASTEXITCODE
 if($code -eq 3){Write-Host "No data was purchased. Review the quote above, then run:" -ForegroundColor Yellow;Write-Host ".\RUN_CANONICAL_PHASE3I_FROZEN_CONFIRMATION.ps1 -ApproveDownload" -ForegroundColor Cyan;return}
 if($code -ne 0){throw "Phase 3I confirmation failed"}
}finally{$env:PYTHONPATH=$old}
$result=Join-Path $env:USERPROFILE "Downloads\TradingPulse_Canonical_Phase3I_Result_20260823.zip"
tar.exe -a -c -f $result -C $PSScriptRoot "research_data\v7\phase3i_confirmation" "research_data\v7\forward_2026\GC_2026_download_quote.json" "config\phase3i_frozen_hypothesis.json"
if($LASTEXITCODE -ne 0){throw "Result packaging failed"}
Write-Host "RESULT ZIP READY: $result" -ForegroundColor Green;Write-Host "PHASE 3I COMPLETE" -ForegroundColor Green
