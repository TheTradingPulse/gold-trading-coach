$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "Trading Pulse Canonical Phase 3D/E - Native R:R and Filter Lab" -ForegroundColor Cyan
Write-Host "Read-only shadow research. No dashboard, detector, grading, or database changes." -ForegroundColor DarkGray

$oldPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = "${PSScriptRoot};${PSScriptRoot}\core"
if ($oldPythonPath) { $env:PYTHONPATH = "$env:PYTHONPATH;$oldPythonPath" }
try {
    & ".\.venv\Scripts\python.exe" -m unittest tests.test_canonical_opportunity_lifecycle -v
    if ($LASTEXITCODE -ne 0) { throw "Lifecycle tests failed" }
    & ".\.venv\Scripts\python.exe" "tools\run_canonical_rr_filter_lab.py"
    if ($LASTEXITCODE -ne 0) { throw "Phase 3D/E lab failed" }
}
finally {
    $env:PYTHONPATH = $oldPythonPath
}

$result = Join-Path $env:USERPROFILE "Downloads\TradingPulse_Canonical_Phase3DE_Result_20260823.zip"
tar.exe -a -c -f $result -C $PSScriptRoot "research_data\v6\canonical_rr_filter_lab"
if ($LASTEXITCODE -ne 0) { throw "Result packaging failed" }
Write-Host "RESULT ZIP READY: $result" -ForegroundColor Green
Write-Host "PHASE 3D/E COMPLETE" -ForegroundColor Green
