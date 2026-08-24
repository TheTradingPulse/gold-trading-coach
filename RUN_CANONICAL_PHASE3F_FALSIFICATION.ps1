$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "Trading Pulse Canonical Phase 3F - Einstein Falsification" -ForegroundColor Cyan
Write-Host "Five-year, cost-adjusted, overlap-purged, multiple-testing-corrected. Shadow only." -ForegroundColor DarkGray

$oldPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = "${PSScriptRoot};${PSScriptRoot}\core"
if ($oldPythonPath) { $env:PYTHONPATH = "$env:PYTHONPATH;$oldPythonPath" }
try {
    & ".\.venv\Scripts\python.exe" -m unittest tests.test_phase3f_math -v
    if ($LASTEXITCODE -ne 0) { throw "Phase 3F tests failed" }
    & ".\.venv\Scripts\python.exe" "tools\run_canonical_phase3f_falsification.py"
    if ($LASTEXITCODE -ne 0) { throw "Phase 3F falsification failed" }
}
finally {
    $env:PYTHONPATH = $oldPythonPath
}

$result = Join-Path $env:USERPROFILE "Downloads\TradingPulse_Canonical_Phase3F_Result_20260823.zip"
tar.exe -a -c -f $result -C $PSScriptRoot "research_data\v6\canonical_phase3f"
if ($LASTEXITCODE -ne 0) { throw "Result packaging failed" }
Write-Host "RESULT ZIP READY: $result" -ForegroundColor Green
Write-Host "PHASE 3F COMPLETE" -ForegroundColor Green
