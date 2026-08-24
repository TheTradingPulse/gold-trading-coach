from __future__ import annotations
import math,re
import pandas as pd
from v4_sniper_features import extract as legacy_extract

SCHEMA="tradingpulse.context.v2"

def _f(v,default=None):
    try:
        x=float(v); return default if math.isnan(x) else x
    except Exception:return default

def _d(obj):
    if obj is None:return {}
    if isinstance(obj,dict):return obj
    return getattr(obj,"__dict__",{}) or {}

def _trend(df):
    if df is None or len(df)<50:return None
    c=df["close"].astype(float); e20=c.ewm(span=20,adjust=False).mean().iloc[-1]; e50=c.ewm(span=50,adjust=False).mean().iloc[-1]
    if c.iloc[-1]>e20>e50:return "bullish"
    if c.iloc[-1]<e20<e50:return "bearish"
    return "mixed"

def _atr_pct(df,n=14):
    if df is None or len(df)<n+1:return None
    h=df["high"].astype(float);l=df["low"].astype(float);c=df["close"].astype(float)
    pc=c.shift(1);tr=pd.concat([(h-l),(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
    atr=tr.rolling(n).mean().iloc[-1];last=c.iloc[-1]
    return round(float(atr/last*100),5) if last else None

def _vol_regime(df):
    if df is None or len(df)<80:return None
    h=df["high"].astype(float);l=df["low"].astype(float);c=df["close"].astype(float);pc=c.shift(1)
    tr=pd.concat([(h-l),(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
    a=tr.rolling(14).mean().dropna()
    if len(a)<50:return None
    cur=float(a.iloc[-1]);med=float(a.iloc[-50:].median())
    if med<=0:return None
    ratio=cur/med
    return "high" if ratio>=1.25 else ("low" if ratio<=.80 else "normal")

def _session_utc(ts):
    t=pd.Timestamp(ts); h=t.hour
    if h<6:return "UTC_00_06"
    if h<12:return "UTC_06_12"
    if h<18:return "UTC_12_18"
    return "UTC_18_24"

def _reason_number(reasons,label):
    pat=re.compile(re.escape(label)+r"[^0-9-]*(-?\d+(?:\.\d+)?)",re.I)
    for r in reasons or []:
        m=pat.search(str(r))
        if m:return _f(m.group(1))
    return None

def _candidate_alias(c,*names):
    for n in names:
        if c.get(n) is not None:return c.get(n)
    return None

def build(candidate,state=None,frames=None,as_of=None):
    """Point-in-time context only. Missing values remain None; no synthetic facts."""
    c=_d(candidate);s=_d(state);frames=frames or {}
    out=legacy_extract(c,s)
    reasons=c.get("reasons") or []
    out.update({
      "schema":SCHEMA,
      "as_of":None if as_of is None else str(as_of),
      "session_utc":_session_utc(as_of) if as_of is not None else None,
      "trend_15m":_trend(frames.get("15m")),"trend_1h":_trend(frames.get("1H")),
      "trend_4h":_trend(frames.get("4H")),"trend_d":_trend(frames.get("D")),
      "atr_pct_15m":_atr_pct(frames.get("15m")),"atr_pct_1h":_atr_pct(frames.get("1H")),
      "volatility_15m":_vol_regime(frames.get("15m")),
      "zone_quality":_f(_candidate_alias(c,"zone_quality","quality_score")),
      "zone_freshness":_f(_candidate_alias(c,"zone_freshness","freshness_score","freshness")),
      "zone_retests":_f(_candidate_alias(c,"retests","retest_count","zone_retests")),
      "zone_width":_f(_candidate_alias(c,"zone_width","width")),
      "opposing_room_points":_f(_candidate_alias(c,"opposing_room_points","room_to_opposition_points")),
      "projected_rr":_f(_candidate_alias(c,"projected_rr","rr")),
      "lifecycle":_candidate_alias(c,"lifecycle"),
      "grade":_candidate_alias(c,"grade"),
      "is_actionable":bool(c.get("is_actionable",False)),
      "reason_zone_quality":_reason_number(reasons,"Zone quality"),
      "reason_local_trend":_reason_number(reasons,"Local trend alignment contributes"),
      "reason_htf":_reason_number(reasons,"Higher-timeframe context contributes"),
      "reason_lifecycle":_reason_number(reasons,"Lifecycle"),
      "reason_nesting":_reason_number(reasons,"Multi-timeframe nesting contributes"),
      "reason_room":_reason_number(reasons,"Room to opposing structure contributes"),
      "reason_width":_reason_number(reasons,"Zone width efficiency contributes"),
    })
    trends=[out.get("trend_1h"),out.get("trend_4h"),out.get("trend_d")]
    direction=str(out.get("direction") or "").upper(); want="bullish" if direction=="LONG" else "bearish"
    known=[x for x in trends if x is not None]
    out["htf_aligned_count"]=sum(x==want for x in known) if known else None
    out["htf_known_count"]=len(known)
    excluded={"schema","symbol","setup_type","direction","as_of"}
    vals=[v for k,v in out.items() if k not in excluded]
    out["feature_completeness"]=round(sum(v is not None and v!="" for v in vals)/max(1,len(vals)),3)
    return out
