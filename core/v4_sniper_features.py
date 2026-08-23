from __future__ import annotations
import math

def _f(x,default=None):
    try:return float(x)
    except:return default

def extract(candidate, state=None):
    """Create stable, model-agnostic contextual features from canonical candidate/state.
    Missing features stay missing; they are never invented."""
    c=candidate if isinstance(candidate,dict) else getattr(candidate,"__dict__",{})
    s=state if isinstance(state,dict) else (getattr(state,"__dict__",{}) if state is not None else {})
    entry=_f(c.get("entry")); stop=_f(c.get("stop"))
    risk=abs(entry-stop) if entry is not None and stop is not None else None
    out={
      "symbol":str(c.get("symbol") or s.get("symbol") or "").upper(),
      "setup_type":str(c.get("setup_type") or c.get("zone_type") or "").lower(),
      "direction":str(c.get("direction") or c.get("side") or "").upper(),
      "score10":_f(c.get("score10",c.get("setup_score"))),
      "risk_points":risk,
    }
    aliases={
      "trend_regime":("trend_regime","trend","regime"),
      "volatility_regime":("volatility_regime","vol_regime"),
      "session":("session","market_session"),
      "htf_alignment":("htf_alignment","higher_timeframe_alignment"),
      "zone_freshness":("zone_freshness","freshness"),
      "zone_strength":("zone_strength","strength"),
      "entry_depth":("entry_depth","zone_entry_depth"),
      "distance_vwap":("distance_vwap","vwap_distance"),
      "distance_ema":("distance_ema","ema_distance"),
      "opposing_structure_r":("opposing_structure_r","room_to_opposition_r"),
      "displacement":("displacement","impulse_strength"),
    }
    for dest,names in aliases.items():
        v=None
        for src in (c,s):
            for n in names:
                if n in src and src[n] is not None:
                    v=src[n];break
            if v is not None:break
        out[dest]=v
    out["feature_completeness"]=round(sum(v is not None and v!="" for k,v in out.items()
        if k not in ("symbol","setup_type","direction"))/max(1,len(out)-3),3)
    return out
