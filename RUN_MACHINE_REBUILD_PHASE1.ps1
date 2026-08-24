$ErrorActionPreference="Stop"
$Root="C:\TradingPulse"
$Python=Join-Path $Root ".venv\Scripts\python.exe"
$Script=Join-Path $Root "tools\resolve_intrabar_evidence.py"
if(-not(Test-Path $Python)){throw "Python environment not found: $Python"}
if(-not(Test-Path $Script)){throw "Phase 1 resolver not found: $Script"}
Set-Location $Root
& $Python $Script --root $Root
if($LASTEXITCODE-ne 0){throw "Phase 1 failed with exit code $LASTEXITCODE"}
