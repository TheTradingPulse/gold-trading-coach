$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Trading Pulse Phase 3K - Five-Year Micro Data Quote" -ForegroundColor Cyan
Write-Host "Quote only. This package cannot purchase data." -ForegroundColor DarkGray

$oldPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = "${PSScriptRoot};${PSScriptRoot}\core"
if ($oldPythonPath) { $env:PYTHONPATH = "$env:PYTHONPATH;$oldPythonPath" }

try {
    & ".\.venv\Scripts\python.exe" -m unittest tests.test_phase3k_quote -v
    if ($LASTEXITCODE -ne 0) { throw "Phase 3K safety tests failed" }

    & ".\.venv\Scripts\python.exe" "tools\run_phase3k_micro_5y_quote.py"
    if ($LASTEXITCODE -ne 0) { throw "Phase 3K quote failed" }
}
finally {
    $env:PYTHONPATH = $oldPythonPath
}

$result = Join-Path $env:USERPROFILE "Downloads\TradingPulse_Canonical_Phase3K_Micro_5Y_Quote_Result_20260823.zip"
tar.exe -a -c -f $result -C $PSScriptRoot "research_data\v7\acquisition\phase3k_micro_5y_quote.json"
if ($LASTEXITCODE -ne 0) { throw "Phase 3K result packaging failed" }

Write-Host "RESULT ZIP READY: $result" -ForegroundColor Green
Write-Host "NO DATA PURCHASED" -ForegroundColor Green
