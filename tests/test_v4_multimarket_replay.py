import sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_market_warehouse import MarketWarehouse
from v4_outcome_engine import evaluate_outcome
from v4_canonical_replay import UNIVERSE
from v4_evidence_analytics import evidence_report

def test_universe():
    assert UNIVERSE==("GC","SI","ES","NQ","YM","RTY","CL","NG")

def test_outcome_long_stop_conservative():
    idx=pd.date_range("2026-01-01",periods=2,freq="15min",tz="UTC")
    f=pd.DataFrame({"open":[100,100],"high":[103,101],"low":[98,99],"close":[101,100],"volume":[1,1]},index=idx)
    c={"direction":"LONG","entry":100,"stop":99,"t1":102}
    r=evaluate_outcome(c,f)
    assert r["entered"] and r["outcome"]=="T1_THEN_STOP"

def test_outcome_not_triggered():
    idx=pd.date_range("2026-01-01",periods=2,freq="15min",tz="UTC")
    f=pd.DataFrame({"open":[100,100],"high":[101,101],"low":[99,99],"close":[100,100],"volume":[1,1]},index=idx)
    assert evaluate_outcome({"direction":"LONG","entry":105,"stop":104,"t1":107},f)["outcome"]=="NOT_TRIGGERED"

def test_warehouse_boundary(tmp_path):
    wh=MarketWarehouse(tmp_path/"w.db")
    idx=pd.date_range("2026-01-01",periods=5,freq="15min",tz="UTC")
    df=pd.DataFrame({"open":[1]*5,"high":[2]*5,"low":[.5]*5,"close":[1.5]*5,"volume":[1]*5},index=idx)
    wh.upsert("ES","15m",df)
    x=wh.read("ES","15m",as_of=idx[2])
    assert len(x)==3 and x.index.max()==idx[2]
