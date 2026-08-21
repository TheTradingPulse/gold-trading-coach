"""
Trading Pulse V3.0F - point-in-time backtest harness.

The harness is intentionally strategy-agnostic: it calls a supplied detector
with ONLY the historical frame available as-of each evaluation timestamp.
Production setup grading can therefore be plugged in without future leakage.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from typing import Callable,Iterable,Any
import pandas as pd

ENGINE_VERSION="3.0F"

@dataclass(frozen=True)
class BacktestEvent:
    symbol:str; timeframe:str; timestamp:str; candidate_id:str
    score:float; side:str; entry:float; stop:float; target:float
    outcome:str; r_multiple:float|None; bars_to_resolution:int|None
    def to_dict(self): return asdict(self)

def resolve_trade(future:pd.DataFrame,side:str,entry:float,stop:float,target:float):
    """Conservative same-bar policy: if stop and target both touch, STOP wins."""
    entered=False
    for n,(_,bar) in enumerate(future.iterrows(),start=1):
        lo=float(bar.Low); hi=float(bar.High)
        if not entered:
            if lo<=entry<=hi: entered=True
            else: continue
        stop_hit=lo<=stop if side=="LONG" else hi>=stop
        target_hit=hi>=target if side=="LONG" else lo<=target
        if stop_hit: return "STOP",-1.0,n
        if target_hit:
            risk=abs(entry-stop); reward=abs(target-entry)
            return "TARGET",(reward/risk if risk else None),n
    return ("OPEN",None,None) if entered else ("NOT_ENTERED",None,None)

def run_point_in_time_backtest(symbol:str,timeframe:str,history:pd.DataFrame,
                               detector:Callable[[pd.DataFrame,str,str],Iterable[Any]],
                               warmup_bars:int=250,forward_bars:int=100):
    x=history.sort_index()
    events=[]
    seen=set()
    for i in range(int(warmup_bars),max(int(warmup_bars),len(x)-1)):
        asof=x.iloc[:i+1].copy()              # NO FUTURE DATA GIVEN TO DETECTOR
        candidates=list(detector(asof,symbol,timeframe) or [])
        for c in candidates:
            cid=str(c["candidate_id"] if isinstance(c,dict) else c.candidate_id)
            key=(cid,x.index[i])
            if key in seen: continue
            seen.add(key)
            get=lambda k: c[k] if isinstance(c,dict) else getattr(c,k)
            entry=float(get("entry")); stop=float(get("stop")); target=float(get("target"))
            side=str(get("side")).upper(); score=float(get("score"))
            future=x.iloc[i+1:min(len(x),i+1+int(forward_bars))]
            outcome,r,bars=resolve_trade(future,side,entry,stop,target)
            events.append(BacktestEvent(symbol,timeframe,x.index[i].isoformat(),cid,score,side,
                                        entry,stop,target,outcome,r,bars))
    return events

def summarize(events):
    rows=[e.to_dict() if hasattr(e,"to_dict") else dict(e) for e in events]
    resolved=[r for r in rows if r["outcome"] in ("TARGET","STOP")]
    wins=[r for r in resolved if r["outcome"]=="TARGET"]
    rs=[float(r["r_multiple"]) for r in resolved if r["r_multiple"] is not None]
    return {"events":len(rows),"resolved":len(resolved),"wins":len(wins),
            "win_rate":round(len(wins)/len(resolved)*100,2) if resolved else None,
            "avg_r":round(sum(rs)/len(rs),4) if rs else None}
