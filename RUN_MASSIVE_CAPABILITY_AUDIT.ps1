param()

$ErrorActionPreference = "Stop"
$root = "C:\TradingPulse"

Set-Location $root

Write-Host "Trading Pulse Massive Capability Audit" -ForegroundColor Cyan
Write-Host "Read-only entitlement checks. No purchases or bulk downloads." -ForegroundColor DarkGray

if (-not $env:MASSIVE_API_KEY) {
    $env:MASSIVE_API_KEY = [Environment]::GetEnvironmentVariable("MASSIVE_API_KEY", "User")
}

if (-not $env:MASSIVE_API_KEY) {
    throw "MASSIVE_API_KEY is not configured."
}

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "TradingPulse virtual-environment Python was not found."
}

& $python "tools\run_massive_capability_audit.py"
if ($LASTEXITCODE -ne 0) {
    throw "Massive capability audit failed."
}

$latest = Get-ChildItem "$root\research_data\v7\massive\capability_audit" -Directory |
    Sort-Object Name -Descending |
    Select-Object -First 1

if (-not $latest) {
    throw "Audit output directory was not created."
}

$result = Join-Path $env:USERPROFILE "Downloads\TradingPulse_Massive_Capability_Audit_Result_20260824.zip"
if (Test-Path $result) {
    Remove-Item -LiteralPath $result -Force
}

Compress-Archive -Path (Join-Path $latest.FullName "*") -DestinationPath $result -Force

Write-Host "RESULT ZIP READY: $result" -ForegroundColor Green
Write-Host "MASSIVE CAPABILITY AUDIT COMPLETE" -ForegroundColor Green
