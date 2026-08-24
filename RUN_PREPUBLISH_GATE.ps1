$ErrorActionPreference = "Stop"
$root = "C:\TradingPulse"
$python = Join-Path $root ".venv\Scripts\python.exe"

Set-Location $root
Write-Host "Trading Pulse Pre-Publish Gate" -ForegroundColor Cyan
Write-Host "No commit or push occurs unless every safety check passes." -ForegroundColor DarkGray

if (-not (Test-Path $python)) {
    throw "TradingPulse virtual environment was not found."
}

& $python "tools\prepublish_gate.py"
if ($LASTEXITCODE -ne 0) {
    throw "PRE-PUBLISH GATE FAILED. Do not stage, commit, or push."
}

& $python -c "import pytest" 2>$null
if ($LASTEXITCODE -eq 0) {
    & $python -m pytest -q tests
    if ($LASTEXITCODE -ne 0) {
        throw "PYTEST GATE FAILED. Do not stage, commit, or push."
    }
} else {
    Write-Host "pytest unavailable; running unittest discovery fallback." -ForegroundColor Yellow
    & $python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) {
        throw "UNIT TEST GATE FAILED. Do not stage, commit, or push."
    }
}

Write-Host "PRE-PUBLISH GATE PASSED" -ForegroundColor Green
Write-Host "Git staging remains a separate manual step." -ForegroundColor Green
