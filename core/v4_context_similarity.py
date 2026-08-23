from __future__ import annotations
from collections import defaultdict
from v4_calibration_engine import _stats, score_bucket

CATEGORICAL=("symbol","setup_type","direction","trend_regime","volatility_regime","session","htf_alignment")
NUMERIC=("zone_freshness","zone_strength","entry_depth","distance_vwap","distance_ema","opposing_structure_r","displacement")

def _same(a,b): return a is not None and b is not None and str(a).lower()==str(b).lower()

def similarity(a,b):
    # Exact identity features dominate. Context refines rather than overrides market/setup identity.
    score=0.0; weight=0.0
    weights={"symbol":4,"setup_type":4,"direction":4,"trend_regime":2,"volatility_regime":1.5,"session":1,"htf_alignment":2}
    for k in CATEGORICAL:
        if a.get(k) is None or b.get(k) is None:continue
        w=weights[k];weight+=w
        if _same(a.get(k),b.get(k)):score+=w
    for k in NUMERIC:
        av=a.get(k);bv=b.get(k)
        try:av=float(av);bv=float(bv)
        except:continue
        weight+=1
        scale=max(abs(av),abs(bv),1.0)
        score+=max(0.0,1-abs(av-bv)/scale)
    return score/weight if weight else 0.0

def nearest(rows, feature, limit=500, minimum=.55):
    ranked=[]
    for r in rows:
        rf=r.get("_features",r)
        s=similarity(feature,rf)
        if s>=minimum: ranked.append((s,r))
    ranked.sort(key=lambda x:x[0],reverse=True)
    return [r for _,r in ranked[:limit]]

def evidence(rows):
    return _stats(rows) if rows else {"n":0,"triggered":0,"hit_3r":0,"hit_5r":0,
      "hit_3r_pct":0,"hit_5r_pct":0}
