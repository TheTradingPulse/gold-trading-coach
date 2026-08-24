$ErrorActionPreference = 'Stop'
Set-Location C:\TradingPulse
$py = '.\.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { throw 'C:\TradingPulse virtualenv Python not found.' }
$logDir='research_data\v4\overnight_deep_dive'; New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log=Join-Path $logDir ('overnight_'+(Get-Date -Format 'yyyyMMdd_HHmmss')+'.log')
function Run-Step([string]$name,[scriptblock]$cmd){
  "`n===== $name =====" | Tee-Object -FilePath $log -Append
  & $cmd 2>&1 | Tee-Object -FilePath $log -Append
  if ($LASTEXITCODE -ne 0){ throw "$name failed. See $log" }
}
"V4 OVERNIGHT DEEP DIVE - RESEARCH ONLY" | Tee-Object -FilePath $log
Run-Step '1/5 REGRESSION' { & $py -m pytest -q }
Run-Step '2/5 DENSE 15M CONTEXT REPLAY' { & $py scripts\v4_run_contextual_replay.py --symbol ALL --timeframe 15m --step 4 --warmup 250 --future-bars 240 --max-events 160 --evidence research_data\v4\context_evidence_v4.db }
Run-Step '3/5 DEEP 1H HISTORICAL CONTEXT REPLAY' { & $py scripts\v4_run_contextual_replay.py --symbol ALL --timeframe 1H --step 16 --warmup 250 --future-bars 120 --max-events 500 --evidence research_data\v4\context_evidence_v4.db }
Run-Step '4/5 OOS CONTEXT / SCORE DEEP DIVE' { & $py scripts\v4_overnight_deep_dive.py --db research_data\v4\context_evidence_v4.db --out research_data\v4\overnight_deep_dive --min-triggered 30 }
Run-Step '5/5 STATUS' { & $py scripts\v4_overnight_status.py }
"`n============================================" | Tee-Object -FilePath $log -Append
" V4 OVERNIGHT DEEP DIVE COMPLETE" | Tee-Object -FilePath $log -Append
"============================================" | Tee-Object -FilePath $log -Append
"RESEARCH ONLY - NO SCORING AUTO-CHANGED" | Tee-Object -FilePath $log -Append
"NO COMMIT / NO PUSH / NO DEPLOY" | Tee-Object -FilePath $log -Append
"LOG: $log" | Tee-Object -FilePath $log -Append
