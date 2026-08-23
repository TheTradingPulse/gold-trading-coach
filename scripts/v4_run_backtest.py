import sys,json,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_multimarket_backtester import MultiMarketBacktester
from v4_canonical_replay import UNIVERSE
from v4_evidence_analytics import evidence_report
p=argparse.ArgumentParser()
p.add_argument("--symbol",default="ALL");p.add_argument("--timeframe",default="15m")
p.add_argument("--step",type=int,default=16);p.add_argument("--warmup",type=int,default=250)
p.add_argument("--future-bars",type=int,default=240);p.add_argument("--min-score",type=float)
p.add_argument("--actionable-only",action="store_true");p.add_argument("--max-events",type=int)
a=p.parse_args();bt=MultiMarketBacktester()
symbols=UNIVERSE if a.symbol.upper()=="ALL" else (a.symbol.upper(),)
for s in symbols:
    r=bt.run_symbol(s,timeframe=a.timeframe,step=a.step,warmup=a.warmup,future_bars=a.future_bars,
                    min_score=a.min_score,actionable_only=a.actionable_only,max_events=a.max_events)
    print(json.dumps(r,indent=2,default=str))
print("EVIDENCE")
print(json.dumps(evidence_report(),indent=2,default=str))
