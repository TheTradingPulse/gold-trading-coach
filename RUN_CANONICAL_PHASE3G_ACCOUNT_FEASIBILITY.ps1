$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "Trading Pulse Canonical Phase 3G v2 - Apex 50K Nominal-Risk Feasibility" -ForegroundColor Cyan
Write-Host "1%=$500, 2%=$1,000, 3%=$1,500. Apex limits remain separate warnings. Shadow only." -ForegroundColor DarkGray
$oldPythonPath=$env:PYTHONPATH
$env:PYTHONPATH="${PSScriptRoot};${PSScriptRoot}\core"
if($oldPythonPath){$env:PYTHONPATH="$env:PYTHONPATH;$oldPythonPath"}
try{
  & ".\.venv\Scripts\python.exe" -m unittest tests.test_account_risk_engine -v
  if($LASTEXITCODE -ne 0){throw "Account risk tests failed"}
  & ".\.venv\Scripts\python.exe" "tools\run_phase3g_account_feasibility.py"
  if($LASTEXITCODE -ne 0){throw "Phase 3G lab failed"}
}finally{$env:PYTHONPATH=$oldPythonPath}
$result=Join-Path $env:USERPROFILE "Downloads\TradingPulse_Canonical_Phase3G_v2_Result_20260823.zip"
tar.exe -a -c -f $result -C $PSScriptRoot "research_data\v6\canonical_phase3g" "core\account_risk_engine.py" "config\account_profiles.json"
if($LASTEXITCODE -ne 0){throw "Result packaging failed"}
Write-Host "RESULT ZIP READY: $result" -ForegroundColor Green
Write-Host "PHASE 3G COMPLETE" -ForegroundColor Green
