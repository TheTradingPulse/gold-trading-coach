$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "Trading Pulse Canonical Phase 3C - Opportunity Lifecycle" -ForegroundColor Cyan
Write-Host "Shadow-only. Dashboard and research databases remain unchanged." -ForegroundColor DarkGray

# Ensure scripts launched from subfolders can import the project-level core package.
$previousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = if ($previousPythonPath) { "$PSScriptRoot;$previousPythonPath" } else { $PSScriptRoot }

$backupRoot = Join-Path $PSScriptRoot "backups\canonical_phase3c_20260823"
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
@("core\canonical_opportunity_lifecycle.py", "config\tradingpulse_registry.json") | ForEach-Object {
    $source = Join-Path $PSScriptRoot $_
    if (Test-Path -LiteralPath $source) {
        $safeName = $_ -replace '[\\/:*?"<>|]', '_'
        Copy-Item -LiteralPath $source -Destination (Join-Path $backupRoot $safeName) -Force
    }
}

try {
    & ".\.venv\Scripts\python.exe" -m unittest tests.test_canonical_opportunity_lifecycle -v
    if ($LASTEXITCODE -ne 0) { throw "Lifecycle tests failed" }

    & ".\.venv\Scripts\python.exe" "tools\run_canonical_lifecycle_shadow.py"
    if ($LASTEXITCODE -ne 0) { throw "Lifecycle shadow failed" }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}

$result = Join-Path $env:USERPROFILE "Downloads\TradingPulse_Canonical_Phase3C_Result_20260823.zip"
tar.exe -a -c -f $result -C $PSScriptRoot "research_data\v6\canonical_lifecycle" "config\tradingpulse_registry.json"
if ($LASTEXITCODE -ne 0) { throw "Result packaging failed" }
Write-Host "RESULT ZIP READY: $result" -ForegroundColor Green
Write-Host "BACKUP: $backupRoot" -ForegroundColor DarkGray
Write-Host "PHASE 3C COMPLETE" -ForegroundColor Green
