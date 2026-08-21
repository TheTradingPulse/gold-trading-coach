"""
Trading Pulse V3.1B - canonical replay adapter.

Builds MarketState from an explicitly supplied point-in-time frame bundle and
runs the production setup candidate engine against it. No network calls are
permitted inside the replay adapter.
"""
from __future__ import annotations
from typing import Mapping
import pandas as pd
from point_in_time_market_state import build_market_state_from_frames
from setup_candidate_engine import build_setup_candidates

ENGINE_VERSION="3.1B"

def replay_candidates(symbol:str,frames:Mapping[str,pd.DataFrame],asof=None):
    clean={}
    for tf,df in frames.items():
        x=df.copy().sort_index()
        if asof is not None:
            ts=pd.Timestamp(asof)
            if isinstance(x.index,pd.DatetimeIndex):
                if x.index.tz is not None and ts.tzinfo is None: ts=ts.tz_localize(x.index.tz)
                elif x.index.tz is None and ts.tzinfo is not None: ts=ts.tz_localize(None)
            x=x.loc[x.index<=ts]
        clean[tf]=x
    state=build_market_state_from_frames(symbol,clean,as_of=asof)
    candidates=build_setup_candidates(state)
    return state,candidates

def detector_for_backtest(frame:pd.DataFrame,symbol:str,timeframe:str):
    # Single-timeframe compatibility adapter. Full research runs should provide
    # synchronized MTF frames through replay_candidates().
    _,cands=replay_candidates(symbol,{timeframe:frame},asof=frame.index[-1])
    rows=[]
    for c in cands:
        if c.timeframe!=timeframe: continue
        if c.projected_entry is None or c.projected_stop is None or c.projected_target is None: continue
        rows.append({"candidate_id":c.candidate_id,"score":round(float(c.setup_score)/10,2),
                     "side":"LONG" if c.zone_type=="demand" else "SHORT",
                     "entry":float(c.projected_entry),"stop":float(c.projected_stop),
                     "target":float(c.projected_target)})
    return rows
