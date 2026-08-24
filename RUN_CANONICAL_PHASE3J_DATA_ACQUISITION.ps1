param(
    [switch]$ApproveCore,
    [double]$MaxCostUSD = 25.00
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Trading Pulse Phase 3J - Controlled Data Acquisition" -ForegroundColor Cyan
Write-Host "2026 standard and actual micro one-minute data; quote and hard cap enforced." -ForegroundColor DarkGray

$oldPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = "${PSScriptRoot};${PSScriptRoot}\core"
if ($oldPythonPath) { $env:PYTHONPATH = "$env:PYTHONPATH;$oldPythonPath" }

try {
    & ".\.venv\Scripts\python.exe" -m unittest tests.test_phase3j_acquisition -v
    if ($LASTEXITCODE -ne 0) { throw "Phase 3J safety tests failed" }

    $runnerArgs = @(
        "tools\run_phase3j_data_acquisition.py",
        "--max-cost-usd", $MaxCostUSD.ToString([Globalization.CultureInfo]::InvariantCulture)
    )
    if ($ApproveCore) { $runnerArgs += "--approve-core" }

    & ".\.venv\Scripts\python.exe" @runnerArgs
    $code = $LASTEXITCODE

    if ($code -eq 3) {
        Write-Host "No data was purchased. Review the quote and rerun with:" -ForegroundColor Yellow
        Write-Host ".\RUN_CANONICAL_PHASE3J_DATA_ACQUISITION.ps1 -ApproveCore -MaxCostUSD 25" -ForegroundColor Cyan
        return
    }
    if ($code -eq 4) {
        throw "Quoted cost exceeded the hard cap. Nothing was purchased."
    }
    if ($code -ne 0) { throw "Phase 3J acquisition failed" }
}
finally {
    $env:PYTHONPATH = $oldPythonPath
}

$result = Join-Path $env:USERPROFILE "Downloads\TradingPulse_Canonical_Phase3J_Acquisition_Result_20260823.zip"
tar.exe -a -c -f $result -C $PSScriptRoot "research_data\v7\acquisition\phase3j_quote.json" "research_data\v7\acquisition\phase3j_manifest.json"
if ($LASTEXITCODE -ne 0) { throw "Phase 3J result packaging failed" }

Write-Host "RESULT ZIP READY: $result" -ForegroundColor Green
Write-Host "PHASE 3J ACQUISITION COMPLETE" -ForegroundColor Green
