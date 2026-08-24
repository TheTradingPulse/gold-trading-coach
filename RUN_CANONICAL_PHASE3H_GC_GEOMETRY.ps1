$ErrorActionPreference="Stop";Set-Location $PSScriptRoot
Write-Host "Trading Pulse Canonical Phase 3H - GC Execution Geometry" -ForegroundColor Cyan
Write-Host "Five-year one-minute fill/entry/stop replay. 2025 remains report-only." -ForegroundColor DarkGray
$old=$env:PYTHONPATH;$env:PYTHONPATH="${PSScriptRoot};${PSScriptRoot}\core";if($old){$env:PYTHONPATH="$env:PYTHONPATH;$old"}
try{
 & ".\.venv\Scripts\python.exe" -m unittest tests.test_phase3h_geometry -v
 if($LASTEXITCODE -ne 0){throw "Phase 3H tests failed"}
 & ".\.venv\Scripts\python.exe" "tools\run_phase3h_gc_geometry.py"
 if($LASTEXITCODE -ne 0){throw "Phase 3H replay failed"}
}finally{$env:PYTHONPATH=$old}
$result=Join-Path $env:USERPROFILE "Downloads\TradingPulse_Canonical_Phase3H_Result_20260823.zip"
tar.exe -a -c -f $result -C $PSScriptRoot "research_data\v6\canonical_phase3h"
if($LASTEXITCODE -ne 0){throw "Result packaging failed"}
Write-Host "RESULT ZIP READY: $result" -ForegroundColor Green;Write-Host "PHASE 3H COMPLETE" -ForegroundColor Green
