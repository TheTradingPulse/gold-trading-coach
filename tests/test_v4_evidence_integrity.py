import sys,sqlite3
from pathlib import Path
import pandas as pd
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/"core"))
from v4_score_contract import score10,score100,tier
from v4_outcome_engine import evaluate_outcome
def test_score_contract():
 c={"setup_score":89,"timeframe":"15m","lifecycle":"APPROACHING","zone_quality_score":90,"freshness_score":90,"retest_count":0,"projected_rr":3}
 assert score10(c)==8.9 and score100(c)==89 and tier(c)=="WATCH_STRUCTURAL"
 c["setup_score"]=90;assert tier(c)=="ELITE_STRUCTURAL"
def test_score_already_10():assert score10({"setup_score":9.2})==9.2 and score100({"setup_score":9.2})==92
def test_geometry_r():
 i=pd.date_range("2026-01-01",periods=2,freq="15min",tz="UTC");f=pd.DataFrame({"open":[100]*2,"high":[104]*2,"low":[100]*2,"close":[103]*2},index=i)
 r=evaluate_outcome({"direction":"LONG","entry":100,"stop":98,"t1":103},f);assert r["target_r"]["T1"]==1.5 and r["achieved_r"]==1.5 and r["realized_r"] is None
def test_ambiguity():
 i=pd.date_range("2026-01-01",periods=1,freq="15min",tz="UTC");f=pd.DataFrame({"open":[100],"high":[103],"low":[98],"close":[101]},index=i)
 r=evaluate_outcome({"direction":"LONG","entry":100,"stop":99,"t1":102},f);assert r["outcome"]=="T1_THEN_STOP" and r["same_bar_ambiguous"] and r["realized_r"]==-1
