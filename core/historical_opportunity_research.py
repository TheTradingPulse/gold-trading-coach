"""Trading Pulse V3.4 Pass 4 - historical WATCH/ELITE evidence engine.

Replays synchronized point-in-time MarketState snapshots, applies the V3.4E
opportunity policy, resolves outcomes conservatively, and produces evidence
analytics. Research only: no broker, journal, live-provider, commit or deploy.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from collections import defaultdict
from typing import Any, Mapping
import math
import pandas as pd

from canonical_replay_adapter import replay_candidates
from opportunity_policy import classify_fields, STRUCTURAL_TIMEFRAMES, CONFIRMATION_TIMEFRAMES

ENGINE_VERSION = "3.4-PASS4"
CONTEXT_TIMEFRAMES = ("M", "W", "D", "4H", "1H")
TF_PRIORITY = {"D": 6, "4H": 5, "1H": 4, "15m": 3, "5m": 2, "1m": 1}

@dataclass(frozen=True)
class HistoricalOpportunity:
    symbol: str; timeframe: str; timestamp: str; candidate_id: str
    tier: str; score: float; composite_score: float; side: str
    entry: float; stop: float; target: float; projected_rr: float
    lifecycle: str; zone_quality: float; freshness: float; retests: int
    mtf_aligned: int; mtf_total: int; mtf_ratio: float; confirmations: int
    distance_percent: float; outcome: str; r_multiple: float | None
    bars_to_resolution: int | None; mae_r: float | None; mfe_r: float | None
    def to_dict(self): return asdict(self)

def _direction(c): return "LONG" if str(c.zone_type).lower() == "demand" else "SHORT"
def _aligned(direction, trend):
    t = str(trend or "").lower()
    return (direction == "LONG" and t == "bullish") or (direction == "SHORT" and t == "bearish")
def _overlap(a, b):
    alo, ahi = float(a.lower_bound), float(a.upper_bound); blo, bhi = float(b.lower_bound), float(b.upper_bound)
    ov = max(0.0, min(ahi, bhi) - max(alo, blo)); smaller = max(min(ahi-alo, bhi-blo), 1e-12)
    return ov / smaller

def _mtf(c, state):
    d = _direction(c); trends = dict(getattr(state, "trends", {}) or {})
    usable = [str(trends.get(tf, "no_data") or "no_data").lower() for tf in CONTEXT_TIMEFRAMES]
    usable = [t for t in usable if t in ("bullish", "bearish", "neutral")]
    if not usable: return 0, 0, 0.0
    a = sum(1 for t in usable if _aligned(d, t)); return a, len(usable), a / len(usable)

def _confirmation_count(c, all_candidates):
    if str(c.timeframe) not in STRUCTURAL_TIMEFRAMES: return 0
    return sum(1 for x in all_candidates if x is not c and str(x.timeframe) in CONFIRMATION_TIMEFRAMES
               and str(x.zone_type) == str(c.zone_type)
               and str(x.lifecycle).upper() in {"APPROACHING", "IN_ZONE", "QUALIFIED"}
               and float(x.zone_quality_score) >= 75 and _overlap(c, x) >= .35)

def _composite(c, state, confirmations):
    _, t, r = _mtf(c, state)
    tf_bonus = {"D":1.5,"4H":1.25,"1H":1.0,"15m":.75}.get(str(c.timeframe),0.0)
    mtf_bonus = max(0.0,(r-.40)*2.0) if t else 0.0
    confirm_bonus = min(confirmations,2)*.35
    distance_penalty = min(max(float(c.distance_percent)-.35,0.0)*.5,1.0)
    return round(min(100.0,float(c.setup_score)+tf_bonus+mtf_bonus+confirm_bonus-distance_penalty),2)

def qualify_candidate(c, state, all_candidates):
    a,t,r = _mtf(c,state); conf = _confirmation_count(c,all_candidates)
    tier, reason = classify_fields(score=c.setup_score,lifecycle=c.lifecycle,timeframe=c.timeframe,
        zone_quality=c.zone_quality_score,freshness=c.freshness_score,retests=c.retest_count,
        projected_rr=c.projected_rr,mtf_total=t,mtf_ratio=r)
    if tier == "REJECT": return None, reason
    return {"tier":tier,"mtf_aligned":a,"mtf_total":t,"mtf_ratio":r,
            "confirmations":conf,"composite_score":_composite(c,state,conf)}, "qualified"

def resolve_trade_metrics(future: pd.DataFrame, side: str, entry: float, stop: float, target: float):
    """Conservative same-bar policy: STOP wins. MAE/MFE begin after entry is touched."""
    entered=False; risk=abs(entry-stop)
    if risk <= 0: return "INVALID",None,None,None,None
    mae=0.0; mfe=0.0
    for n,(_,bar) in enumerate(future.iterrows(),start=1):
        lo=float(bar.Low); hi=float(bar.High)
        if not entered:
            if lo <= entry <= hi: entered=True
            else: continue
        if side == "LONG":
            adverse=max(0.0,entry-lo); favorable=max(0.0,hi-entry)
            stop_hit=lo<=stop; target_hit=hi>=target
        else:
            adverse=max(0.0,hi-entry); favorable=max(0.0,entry-lo)
            stop_hit=hi>=stop; target_hit=lo<=target
        mae=max(mae,adverse/risk); mfe=max(mfe,favorable/risk)
        if stop_hit: return "STOP",-1.0,n,round(mae,4),round(mfe,4)
        if target_hit: return "TARGET",round(abs(target-entry)/risk,4),n,round(mae,4),round(mfe,4)
    return (("OPEN",None,None,round(mae,4),round(mfe,4)) if entered
            else ("NOT_ENTERED",None,None,None,None))

def _same_idea_key(c):
    # Candidate id is derived from symbol/type/timeframe/zone bounds and therefore
    # persists while the same structural zone remains alive.
    return str(c.candidate_id)

def replay_timeframe(symbol: str, evaluation_tf: str, frames: Mapping[str,pd.DataFrame],
                     warmup_bars: int=250, forward_bars: int=100):
    base=frames.get(evaluation_tf)
    if base is None or base.empty: return [], {"evaluated":0,"qualified":0,"deduped":0,"rejections":{}}
    x=base.sort_index(); events=[]; seen=set(); rejected=defaultdict(int); evaluated=0; qualified=0; deduped=0
    for i in range(int(warmup_bars), max(int(warmup_bars),len(x)-1)):
        ts=x.index[i]
        pit={tf:df.loc[df.index<=ts].copy() for tf,df in frames.items() if df is not None and not df.empty}
        if evaluation_tf not in pit or len(pit[evaluation_tf]) < warmup_bars: continue
        state,candidates=replay_candidates(symbol,pit,asof=ts)
        for c in candidates:
            if str(c.timeframe) != str(evaluation_tf): continue
            evaluated += 1
            q,reason=qualify_candidate(c,state,candidates)
            if q is None: rejected[reason]+=1; continue
            qualified += 1
            idea=_same_idea_key(c)
            if idea in seen: deduped += 1; continue
            seen.add(idea)
            if c.projected_entry is None or c.projected_stop is None or c.projected_target is None or c.projected_rr is None:
                rejected["trade_levels_unavailable"]+=1; continue
            future=x.iloc[i+1:min(len(x),i+1+int(forward_bars))]
            side=_direction(c); outcome,r_mult,bars,mae,mfe=resolve_trade_metrics(
                future,side,float(c.projected_entry),float(c.projected_stop),float(c.projected_target))
            events.append(HistoricalOpportunity(
                str(symbol).upper(),str(c.timeframe),pd.Timestamp(ts).isoformat(),str(c.candidate_id),
                q["tier"],float(c.setup_score),float(q["composite_score"]),side,
                float(c.projected_entry),float(c.projected_stop),float(c.projected_target),float(c.projected_rr),
                str(c.lifecycle),float(c.zone_quality_score),float(c.freshness_score),int(c.retest_count),
                int(q["mtf_aligned"]),int(q["mtf_total"]),float(q["mtf_ratio"]),int(q["confirmations"]),
                float(c.distance_percent),outcome,r_mult,bars,mae,mfe))
    return events,{"evaluated":evaluated,"qualified":qualified,"deduped":deduped,"rejections":dict(rejected)}

def _bucket(v, cuts, labels):
    for cut,label in zip(cuts,labels):
        if v < cut:return label
    return labels[-1]

def _group_stats(rows, key_fn):
    groups=defaultdict(list)
    for r in rows: groups[str(key_fn(r))].append(r)
    return {k:summarize(v,include_breakdowns=False) for k,v in sorted(groups.items())}

def summarize(events, include_breakdowns=True):
    rows=[e.to_dict() if hasattr(e,"to_dict") else dict(e) for e in events]
    resolved=[r for r in rows if r.get("outcome") in ("TARGET","STOP")]
    wins=[r for r in resolved if r.get("outcome")=="TARGET"]; losses=[r for r in resolved if r.get("outcome")=="STOP"]
    rs=[float(r["r_multiple"]) for r in resolved if r.get("r_multiple") is not None]
    pos=sum(x for x in rs if x>0); neg=abs(sum(x for x in rs if x<0))
    maes=[float(r["mae_r"]) for r in resolved if r.get("mae_r") is not None]
    mfes=[float(r["mfe_r"]) for r in resolved if r.get("mfe_r") is not None]
    n=len(resolved)
    warning=("INSUFFICIENT" if n<30 else "LIMITED" if n<100 else "DEVELOPING" if n<300 else "STRONGER_SAMPLE")
    out={"events":len(rows),"resolved":n,"wins":len(wins),"losses":len(losses),
         "win_rate":round(len(wins)/n*100,2) if n else None,
         "expectancy_r":round(sum(rs)/len(rs),4) if rs else None,
         "avg_r":round(sum(rs)/len(rs),4) if rs else None,
         "profit_factor":round(pos/neg,3) if neg else (None if not pos else 999.0),
         "total_r":round(sum(rs),3) if rs else None,
         "avg_mae_r":round(sum(maes)/len(maes),4) if maes else None,
         "avg_mfe_r":round(sum(mfes)/len(mfes),4) if mfes else None,
         "sample_warning":warning,
         "probability_claim_allowed":False}
    if include_breakdowns:
        out["by_tier"]=_group_stats(rows,lambda r:r.get("tier","?"))
        out["by_market"]=_group_stats(rows,lambda r:r.get("symbol","?"))
        out["by_timeframe"]=_group_stats(rows,lambda r:r.get("timeframe","?"))
        out["by_mtf"]=_group_stats(rows,lambda r:_bucket(float(r.get("mtf_ratio") or 0),[.40,.60,.80,1.01],["<40%","40-59%","60-79%","80-100%","80-100%"]))
        out["by_zone_quality"]=_group_stats(rows,lambda r:_bucket(float(r.get("zone_quality") or 0),[80,90,101],["75-79","80-89","90-100","90-100"]))
        out["by_freshness"]=_group_stats(rows,lambda r:_bucket(float(r.get("freshness") or 0),[80,90,101],["70-79","80-89","90-100","90-100"]))
        out["by_confirmations"]=_group_stats(rows,lambda r:min(int(r.get("confirmations") or 0),2))
        out["by_rr"]=_group_stats(rows,lambda r:_bucket(float(r.get("projected_rr") or 0),[2.5,3,4,6,51],["2.0-2.49","2.5-2.99","3.0-3.99","4.0-5.99","6.0+","6.0+"]))
        out["by_lifecycle"]=_group_stats(rows,lambda r:r.get("lifecycle","?"))
    return out
