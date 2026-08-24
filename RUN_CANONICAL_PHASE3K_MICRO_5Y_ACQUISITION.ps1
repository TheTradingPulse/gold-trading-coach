param(
    [switch]$ApprovePurchase,
    [double]$MaxCostUSD = 45.00
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Trading Pulse Phase 3K - Five-Year Micro Acquisition" -ForegroundColor Cyan
Write-Host "2021-2025 micro OHLCV-1m; resume protection and hard cap enforced." -ForegroundColor DarkGray

$oldPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = "${PSScriptRoot};${PSScriptRoot}\core"
if ($oldPythonPath) { $env:PYTHONPATH = "$env:PYTHONPATH;$oldPythonPath" }

try {
    & ".\.venv\Scripts\python.exe" -m unittest tests.test_phase3k_acquisition -v
    if ($LASTEXITCODE -ne 0) { throw "Phase 3K acquisition safety tests failed" }

    $runnerArgs = @(
        "tools\run_phase3k_micro_5y_acquisition.py",
        "--max-cost-usd", $MaxCostUSD.ToString([Globalization.CultureInfo]::InvariantCulture)
    )
    if ($ApprovePurchase) { $runnerArgs += "--approve-purchase" }

    & ".\.venv\Scripts\python.exe" @runnerArgs
    $code = $LASTEXITCODE
    if ($code -eq 3) {
        Write-Host "No data was purchased. Rerun with -ApprovePurchase after reviewing the quote." -ForegroundColor Yellow
        return
    }
    if ($code -eq 4) { throw "Quote exceeded the hard cap. Nothing was purchased." }
    if ($code -eq 5) { throw "Insufficient free disk space. Nothing was purchased." }
    if ($code -ne 0) { throw "Phase 3K acquisition failed" }
}
finally {
    $env:PYTHONPATH = $oldPythonPath
}

$result = Join-Path $env:USERPROFILE "Downloads\TradingPulse_Canonical_Phase3K_Micro_5Y_Acquisition_Result_20260823.zip"
tar.exe -a -c -f $result -C $PSScriptRoot "research_data\v7\acquisition\phase3k_micro_5y_purchase_quote.json" "research_data\v7\acquisition\phase3k_micro_5y_manifest.json"
if ($LASTEXITCODE -ne 0) { throw "Phase 3K result packaging failed" }

Write-Host "RESULT ZIP READY: $result" -ForegroundColor Green
Write-Host "PHASE 3K ACQUISITION COMPLETE" -ForegroundColor Green
