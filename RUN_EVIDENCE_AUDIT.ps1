$ErrorActionPreference = "Stop"
$Root = "C:\TradingPulse"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Script = Join-Path $Root "tools\run_evidence_audit.py"

if (-not (Test-Path $Python)) { throw "Python environment not found: $Python" }
if (-not (Test-Path $Script)) { throw "Audit tool not found: $Script" }

Set-Location $Root
& $Python $Script --root $Root
if ($LASTEXITCODE -ne 0) { throw "Audit failed with exit code $LASTEXITCODE" }
