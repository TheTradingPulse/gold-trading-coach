"""
Trading Pulse V3.1A - historical acquisition adapter.

Downloads provider/reference history into the V3.0E HistoricalStore. This is
research data, not execution data. The adapter is intentionally provider-aware
and returns coverage diagnostics instead of pretending missing intraday history
exists.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from pathlib import Path
import pandas as pd
from instruments import get_instrument
from historical_data_store import HistoricalStore,normalize_history,audit_history

ENGINE_VERSION="3.1A"
TF_PROVIDER={"5m":"5m","15m":"15m","1H":"1h","4H":"1h","D":"1d"}

@dataclass(frozen=True)
class AcquisitionResult:
    symbol:str; timeframe:str; provider:str; rows:int; first:str|None; last:str|None
    requested_period:str; complete:bool; note:str
    def to_dict(self): return asdict(self)

def _download_yahoo(symbol,timeframe,period):
    import yfinance as yf
    inst=get_instrument(symbol)
    interval=TF_PROVIDER[timeframe]
    df=yf.download(inst.data_symbol,period=period,interval=interval,
                   auto_adjust=False,progress=False,threads=False)
    if isinstance(df.columns,pd.MultiIndex):
        df.columns=[c[0] for c in df.columns]
    x=normalize_history(df)
    if timeframe=="4H" and not x.empty:
        # 4H research bars are deterministically aggregated from hourly bars.
        x=x.resample("4h",origin="start_day").agg(
            {"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}
        ).dropna(subset=["Open","High","Low","Close"])
    return x

def acquire(symbol,timeframe,store_root="research_data/history",period=None,provider="yahoo"):
    tf=str(timeframe)
    if tf not in TF_PROVIDER: raise ValueError(f"Unsupported timeframe: {tf}")
    # Yahoo limits intraday history. We request realistic windows and report them.
    default_period={"5m":"60d","15m":"60d","1H":"730d","4H":"730d","D":"2y"}[tf]
    requested=period or default_period
    if provider!="yahoo": raise ValueError("V3.1A currently implements yahoo research acquisition only")
    x=_download_yahoo(symbol,tf,requested)
    store=HistoricalStore(store_root); merged=store.upsert(symbol,tf,x)
    audit=audit_history(merged,tf)
    note="REFERENCE/RESEARCH DATA ONLY - NOT EXECUTION GRADE"
    complete=bool(len(x)>0)
    return AcquisitionResult(symbol.upper(),tf,"Yahoo Finance",len(merged),audit.first,audit.last,
                             requested,complete,note)

def acquire_universe(symbols,timeframes=("15m","1H","4H","D"),store_root="research_data/history"):
    results=[]; errors={}
    for s in symbols:
        for tf in timeframes:
            try: results.append(acquire(s,tf,store_root=store_root))
            except Exception as exc: errors[f"{s}:{tf}"]=str(exc)
    return {"results":[r.to_dict() for r in results],"errors":errors}

