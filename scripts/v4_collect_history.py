from __future__ import annotations
import argparse, sys, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"core"))
from v4_history_collector import collect, collect_universe
from v4_market_warehouse import MarketWarehouse

p=argparse.ArgumentParser()
p.add_argument("--symbol"); p.add_argument("--timeframe")
p.add_argument("--all",action="store_true"); p.add_argument("--period")
p.add_argument("--db",default="research_data/v4/market_warehouse.db")
a=p.parse_args()
if a.all: result=collect_universe(warehouse_path=a.db)
elif a.symbol and a.timeframe: result=collect(a.symbol,a.timeframe,a.db,a.period)
else: p.error("use --all or --symbol SYMBOL --timeframe TF")
print(json.dumps(result,indent=2,default=str))
print("COVERAGE")
print(json.dumps(MarketWarehouse(a.db).coverage(),indent=2))
