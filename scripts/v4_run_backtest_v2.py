import sys,json,argparse
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/"core"))
from v4_multimarket_backtester import MultiMarketBacktester
from v4_canonical_replay import UNIVERSE
from v4_evidence_analytics import print_report
p=argparse.ArgumentParser();p.add_argument("--symbol",default="ALL");p.add_argument("--timeframe",default="15m");p.add_argument("--step",type=int,default=16);p.add_argument("--warmup",type=int,default=250);p.add_argument("--future-bars",type=int,default=240);p.add_argument("--min-score10",type=float);p.add_argument("--tier");p.add_argument("--max-events",type=int);p.add_argument("--evidence",default="research_data/v4/evidence_v2.db");a=p.parse_args()
b=MultiMarketBacktester(evidence=a.evidence)
for s in (UNIVERSE if a.symbol.upper()=="ALL" else (a.symbol.upper(),)):
 print(json.dumps(b.run_symbol(s,a.timeframe,a.warmup,a.step,a.future_bars,a.min_score10,a.tier,a.max_events),indent=2))
print_report(a.evidence)
