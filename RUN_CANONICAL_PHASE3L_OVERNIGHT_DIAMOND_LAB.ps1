param([double]$Hours = 10.0)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($Hours -lt 0.25 -or $Hours -gt 12.0) {
    throw "Hours must be between 0.25 and 12."
}

Write-Host "Trading Pulse Phase 3L - Overnight Diamond Discovery Lab" -ForegroundColor Cyan
Write-Host "Local-only, resumable, standard/micro consensus, 1R-20R." -ForegroundColor DarkGray
Write-Host "Runtime limit: $Hours hours" -ForegroundColor Cyan

$oldPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = "${PSScriptRoot};${PSScriptRoot}\core"
if ($oldPythonPath) { $env:PYTHONPATH = "$env:PYTHONPATH;$oldPythonPath" }

try {
    & ".\.venv\Scripts\python.exe" -m unittest tests.test_phase3l_diamond_lab -v
    if ($LASTEXITCODE -ne 0) { throw "Phase 3L safety tests failed" }

    & ".\.venv\Scripts\python.exe" "tools\run_phase3l_overnight_diamond_lab.py" `
        "--hours" $Hours.ToString([Globalization.CultureInfo]::InvariantCulture)
    if ($LASTEXITCODE -ne 0) { throw "Phase 3L Diamond Lab failed" }
}
finally {
    $env:PYTHONPATH = $oldPythonPath
}

$result = Join-Path $env:USERPROFILE "Downloads\TradingPulse_Canonical_Phase3L_Diamond_Lab_Result_20260823.zip"
& ".\.venv\Scripts\python.exe" "tools\package_phase3l_result.py" --output $result
if ($LASTEXITCODE -ne 0) { throw "Phase 3L result packaging failed" }

Write-Host "RESULT ZIP READY: $result" -ForegroundColor Green
Write-Host "PHASE 3L COMPLETE" -ForegroundColor Green
