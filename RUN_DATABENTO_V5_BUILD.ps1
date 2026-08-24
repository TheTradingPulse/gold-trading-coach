$ErrorActionPreference="Stop"
$Root="C:\TradingPulse"
$Python=Join-Path $Root ".venv\Scripts\python.exe"
$Script=Join-Path $Root "tools\build_databento_v5_warehouse.py"
if(-not(Test-Path $Python)){throw "Python environment not found: $Python"}
if(-not(Test-Path $Script)){throw "V5 warehouse builder not found: $Script"}
Set-Location $Root
& $Python $Script --root $Root
if($LASTEXITCODE-ne 0){throw "V5 warehouse build failed with exit code $LASTEXITCODE"}
