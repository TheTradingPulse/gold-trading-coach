$ErrorActionPreference = "Stop"
$Root = "C:\TradingPulse"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Script = Join-Path $Root "tools\revalidate_v4_evidence.py"
if (-not (Test-Path $Python)) { throw "Python environment not found: $Python" }
if (-not (Test-Path $Script)) { throw "Revalidator not found: $Script" }
Set-Location $Root
& $Python $Script --root $Root
if ($LASTEXITCODE -ne 0) { throw "Revalidation failed with exit code $LASTEXITCODE" }
