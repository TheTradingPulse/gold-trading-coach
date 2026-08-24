import pandas as pd
from core.v4_blind_metrics import wilson_low, summarize
from core.v4_historical_quality import HistoricalQualityRegistry
def test_wilson():
    assert 0 < wilson_low(65,100) < .65
def test_metrics():
    d=pd.DataFrame({"entered":[1,1,1],"primary_hit":[1,1,0],"stretch_hit":[1,0,0],"realized_r":[3,3,-1]})
    r=summarize(d,3); assert r["trades"]==3 and r["wins"]==2
def test_quality():
    q=HistoricalQualityRegistry(); q.seed_known(["GC"]); assert q.is_flagged("GC","2025-11-28T12:00:00Z")
