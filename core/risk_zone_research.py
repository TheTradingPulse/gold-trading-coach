"""Trading Pulse V3.1D - Risk & Zone Research Engine.

Research-only diagnostics for setup zones and stop/R:R assumptions.
Does NOT change production scoring, trade plans, or execution readiness.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Optional
import math
import pandas as pd

ENGINE_VERSION = "3.1D"
ATR_PERIOD = 14
ATR_BUFFER_FRACTION = 0.20
MIN_BUFFER_TICKS = 2


def _f(v, default=None):
    try:
        x=float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _canonical(df: Optional[pd.DataFrame]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["open","high","low","close","volume"])
    x=df.copy()
    x.columns=[str(c).strip().lower() for c in x.columns]
    for c in ("open","high","low","close"):
        if c not in x.columns:
            raise ValueError(f"history missing required column: {c}")
        x[c]=pd.to_numeric(x[c],errors="coerce")
    if "volume" not in x.columns: x["volume"]=0.0
    x["volume"]=pd.to_numeric(x["volume"],errors="coerce").fillna(0.0)
    return x.dropna(subset=["open","high","low","close"]).sort_index()


def atr_points(df: Optional[pd.DataFrame], period: int=ATR_PERIOD) -> Optional[float]:
    x=_canonical(df)
    if len(x)<2: return None
    prev=x["close"].shift(1)
    tr=pd.concat([(x["high"]-x["low"]).abs(),(x["high"]-prev).abs(),(x["low"]-prev).abs()],axis=1).max(axis=1)
    a=tr.rolling(max(2,int(period)),min_periods=2).mean().iloc[-1]
    return _f(a)


def adaptive_buffer_points(instrument: Any, history: Optional[pd.DataFrame]) -> tuple[float, Optional[float]]:
    tick=float(instrument.tick_size)
    atr=atr_points(history)
    floor=tick*MIN_BUFFER_TICKS
    volatility=(atr*ATR_BUFFER_FRACTION) if atr is not None else 0.0
    raw=max(floor,volatility)
    # Round UP to a valid tick so research never understates risk.
    ticks=max(MIN_BUFFER_TICKS, math.ceil(raw/tick-1e-12))
    return ticks*tick, atr


def candidate_risk_audit(candidate: Any, instrument: Any, history: Optional[pd.DataFrame]=None) -> dict:
    get=lambda k,d=None: candidate.get(k,d) if isinstance(candidate,dict) else getattr(candidate,k,d)
    ztype=str(get("zone_type","")).lower()
    lower=_f(get("lower_bound")); upper=_f(get("upper_bound")); entry=_f(get("projected_entry")); target=_f(get("projected_target"))
    if None in (lower,upper,entry) or ztype not in ("demand","supply"):
        raise ValueError("candidate lacks valid zone/entry fields")
    tick=float(instrument.tick_size); width=upper-lower
    legacy_buffer=tick*2
    legacy_stop=lower-legacy_buffer if ztype=="demand" else upper+legacy_buffer
    adaptive_buffer,atr=adaptive_buffer_points(instrument,history)
    adaptive_stop=lower-adaptive_buffer if ztype=="demand" else upper+adaptive_buffer
    legacy_risk=abs(entry-legacy_stop); adaptive_risk=abs(entry-adaptive_stop)
    room=abs(target-entry) if target is not None else None
    legacy_rr=(room/legacy_risk) if room is not None and legacy_risk>0 else None
    adaptive_rr=(room/adaptive_risk) if room is not None and adaptive_risk>0 else None
    return {
        "candidate_id":str(get("candidate_id","")),"symbol":str(get("symbol",instrument.root_symbol)),"timeframe":str(get("timeframe","")),
        "zone_type":ztype,"setup_score":_f(get("setup_score")),"zone_quality_score":_f(get("zone_quality_score")),
        "zone_lower":lower,"zone_upper":upper,"zone_width_points":width,"zone_width_ticks":width/tick,
        "atr14_points":atr,"zone_width_atr":(width/atr if atr and atr>0 else None),"entry":entry,"target":target,
        "legacy_buffer_points":legacy_buffer,"legacy_buffer_ticks":2,"legacy_stop":legacy_stop,"legacy_risk_points":legacy_risk,"legacy_risk_ticks":legacy_risk/tick,"legacy_rr":legacy_rr,
        "adaptive_buffer_points":adaptive_buffer,"adaptive_buffer_ticks":adaptive_buffer/tick,"adaptive_stop":adaptive_stop,"adaptive_risk_points":adaptive_risk,"adaptive_risk_ticks":adaptive_risk/tick,"adaptive_rr":adaptive_rr,
        "rr_inflation_from_legacy":((legacy_rr/adaptive_rr) if legacy_rr is not None and adaptive_rr not in (None,0) else None),
        "risk_dollars_per_contract_legacy":instrument.dollars_for_points(legacy_risk),"risk_dollars_per_contract_adaptive":instrument.dollars_for_points(adaptive_risk),
    }


def audit_candidates(candidates, instrument, history=None) -> pd.DataFrame:
    rows=[]
    for c in candidates or []:
        try: rows.append(candidate_risk_audit(c,instrument,history))
        except ValueError: continue
    return pd.DataFrame(rows)


def summarize_audit(rows: pd.DataFrame) -> dict:
    if rows is None or rows.empty: return {"samples":0}
    def med(c):
        s=pd.to_numeric(rows[c],errors="coerce").dropna(); return round(float(s.median()),4) if len(s) else None
    return {"samples":int(len(rows)),"median_zone_width_ticks":med("zone_width_ticks"),"median_zone_width_atr":med("zone_width_atr"),
            "median_legacy_risk_ticks":med("legacy_risk_ticks"),"median_adaptive_risk_ticks":med("adaptive_risk_ticks"),
            "median_legacy_rr":med("legacy_rr"),"median_adaptive_rr":med("adaptive_rr"),"median_rr_inflation":med("rr_inflation_from_legacy")}
