"""
Trading Pulse V3.0E - Historical data cache / replay foundation.

Stores normalized OHLCV by symbol + timeframe, validates chronology/gaps,
and supports point-in-time slices. This module does not fetch from a broker;
providers can populate the cache without changing replay/backtest logic.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable
import pandas as pd

ENGINE_VERSION = "3.0E"
REQUIRED = ("Open","High","Low","Close","Volume")

def normalize_history(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=list(REQUIRED))
    x=df.copy()
    if not isinstance(x.index,pd.DatetimeIndex):
        for col in ("Datetime","Date","Timestamp","timestamp","date"):
            if col in x.columns:
                x[col]=pd.to_datetime(x[col],utc=True,errors="coerce")
                x=x.set_index(col); break
    x.index=pd.to_datetime(x.index,utc=True,errors="coerce")
    x=x[~x.index.isna()]
    rename={str(c).lower():c for c in x.columns}
    for need in REQUIRED:
        if need not in x.columns and need.lower() in rename:
            x=x.rename(columns={rename[need.lower()]:need})
    for c in REQUIRED:
        if c not in x.columns: x[c]=0.0 if c=="Volume" else float("nan")
        x[c]=pd.to_numeric(x[c],errors="coerce")
    x=x[list(REQUIRED)].dropna(subset=["Open","High","Low","Close"])
    x=x[~x.index.duplicated(keep="last")].sort_index()
    return x

def interval_minutes(tf: str) -> int:
    return {"5m":5,"15m":15,"1H":60,"4H":240,"D":1440}.get(str(tf),0)

@dataclass(frozen=True)
class HistoryAudit:
    rows:int; duplicates:int; out_of_order:int; invalid_ohlc:int
    large_gaps:int; first:str|None; last:str|None
    def to_dict(self): return asdict(self)

def audit_history(df: pd.DataFrame, timeframe: str) -> HistoryAudit:
    raw=df.copy() if df is not None else pd.DataFrame()
    dup=int(raw.index.duplicated().sum()) if len(raw) else 0
    oo=int((pd.Series(raw.index[1:]).reset_index(drop=True) < pd.Series(raw.index[:-1]).reset_index(drop=True)).sum()) if len(raw)>1 else 0
    x=normalize_history(raw)
    bad=int(((x.High < x.Low)|(x.High < x.Open)|(x.High < x.Close)|(x.Low > x.Open)|(x.Low > x.Close)).sum()) if len(x) else 0
    mins=interval_minutes(timeframe)
    gaps=0
    if mins and len(x)>1:
        delta=x.index.to_series().diff().dt.total_seconds().div(60)
        # deliberately flags only very large discontinuities; session/weekend gaps
        # can be classified by a future exchange-calendar adapter.
        gaps=int((delta > mins*20).sum())
    return HistoryAudit(len(x),dup,oo,bad,gaps,
        x.index[0].isoformat() if len(x) else None,
        x.index[-1].isoformat() if len(x) else None)

class HistoricalStore:
    def __init__(self, root: str|Path):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
    def path(self,symbol,timeframe):
        return self.root/f"{str(symbol).upper()}__{timeframe}.pkl"
    def load(self,symbol,timeframe):
        p=self.path(symbol,timeframe)
        return normalize_history(pd.read_pickle(p)) if p.exists() else normalize_history(pd.DataFrame())
    def upsert(self,symbol,timeframe,df):
        old=self.load(symbol,timeframe)
        new=normalize_history(df)
        merged=normalize_history(pd.concat([old,new]))
        merged.to_pickle(self.path(symbol,timeframe))
        return merged
    def slice_asof(self,symbol,timeframe,asof):
        x=self.load(symbol,timeframe)
        ts=pd.Timestamp(asof)
        ts=ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
        return x.loc[x.index<=ts].copy()
