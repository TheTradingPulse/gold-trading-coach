import sys,json,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_history_collector import collect
from v4_canonical_replay import UNIVERSE
p=argparse.ArgumentParser();p.add_argument("--timeframes",default="15m,1H,4H,D")
p.add_argument("--db",default="research_data/v4/market_warehouse.db");a=p.parse_args()
results=[]
for s in UNIVERSE:
  for tf in [x.strip() for x in a.timeframes.split(",") if x.strip()]:
    r=collect(s,tf,a.db);results.append(r);print(json.dumps(r,default=str))
print("PASS",sum(r.get("status")=="PASS" for r in results),"FAIL",sum(r.get("status")!="PASS" for r in results))
