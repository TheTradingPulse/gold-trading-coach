from __future__ import annotations
from typing import Any
ELITE_SCORE10=9.0
WATCH_SCORE10=8.5
ACTIVE_LIFECYCLES={"IN_ZONE","APPROACHING","QUALIFIED"}
ELITE_TIMEFRAMES={"15m","1H","4H","D","W","M"}
def _f(v,d=None):
    try:return float(v)
    except (TypeError,ValueError):return d
def _g(c,k,d=None): return c.get(k,d) if isinstance(c,dict) else getattr(c,k,d)
def score100(c):
    x=_f(_g(c,"setup_score"),_f(_g(c,"quality_score"),0.0))
    return round(x*10 if x<=10 else x,2)
def score10(c): return round(score100(c)/10,2)
def flags(c):
    rr=_f(_g(c,"projected_rr")); life=str(_g(c,"lifecycle","")).upper()
    return {"score_8_5":score10(c)>=8.5,"score_9_0":score10(c)>=9.0,
      "active":life in ACTIVE_LIFECYCLES,"timeframe_valid":str(_g(c,"timeframe","")) in ELITE_TIMEFRAMES,
      "zone_quality_75":_f(_g(c,"zone_quality_score"),0)>=75,"freshness_70":_f(_g(c,"freshness_score"),0)>=70,
      "retests_le_1":int(_f(_g(c,"retest_count"),0))<=1,"rr_2":rr is not None and 2<=rr<=50}
def tier(c):
    if bool(_g(c,"is_actionable",False)):return "ACTIONABLE"
    x=flags(c); structural=all(x[k] for k in ("active","timeframe_valid","zone_quality_75","freshness_70","retests_le_1","rr_2"))
    if structural and x["score_9_0"]:return "ELITE_STRUCTURAL"
    if structural and x["score_8_5"]:return "WATCH_STRUCTURAL"
    return "CANDIDATE"
