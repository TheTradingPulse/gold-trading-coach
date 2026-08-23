"""Trading Pulse V3.4 multi-instrument reference-data adapter.
Yahoo data is development/reference data only and is never execution eligible.

V3.4 Pass 2A adds a short-lived, process-local raw-frame cache plus optional
parallel prefetching. The cache stores provider frames before timeframe-specific
resampling/tailing so repeated consumers of the same MarketState snapshot do not
redownload identical Yahoo history.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import RLock
import time

import pandas as pd
import yfinance as yf

from instruments import get_instrument

INTERVALS={"1m":"1m","5m":"5m","15m":"15m","1H":"1h","4H":"1h","D":"1d","W":"1wk","M":"1mo"}
PERIODS={"1m":"7d","5m":"60d","15m":"60d","1H":"730d","4H":"730d","D":"10y","W":"10y","M":"max"}

# Long enough to collapse duplicate work inside a dashboard refresh, short enough
# that live 1m state is not silently held for a full Streamlit refresh cycle.
_RAW_CACHE_TTL_SECONDS = 12.0
_RAW_CACHE: dict[tuple[str, str, str], tuple[float, pd.DataFrame | None]] = {}
_RAW_CACHE_LOCK = RLock()


def _normalize(df):
    if df is None or df.empty: return None
    if isinstance(df.columns,pd.MultiIndex): df.columns=df.columns.get_level_values(0)
    df=df.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
    need=["open","high","low","close"]
    if any(c not in df.columns for c in need): return None
    if "volume" not in df.columns: df["volume"]=0.0
    df=df[["open","high","low","close","volume"]].dropna(subset=need)
    df.index=pd.to_datetime(df.index,utc=True); df.index.name="timestamp"
    return df.sort_index()


def _provider_frame(data_symbol: str, interval: str, period: str, force_refresh: bool = False):
    key=(data_symbol, interval, period)
    now=time.monotonic()

    if not force_refresh:
        with _RAW_CACHE_LOCK:
            cached=_RAW_CACHE.get(key)
            if cached is not None and (now-cached[0]) <= _RAW_CACHE_TTL_SECONDS:
                frame=cached[1]
                return None if frame is None else frame.copy(deep=False)

    try:
        frame=yf.download(data_symbol,period=period,interval=interval,progress=False,auto_adjust=False)
    except Exception:
        frame=None

    frame=_normalize(frame)
    with _RAW_CACHE_LOCK:
        _RAW_CACHE[key]=(time.monotonic(), frame)
    return None if frame is None else frame.copy(deep=False)


def fetch_market_data(symbol:str,timeframe:str,limit:int=500,as_of=None,force_refresh:bool=False):
    inst=get_instrument(symbol); tf=str(timeframe)
    interval=INTERVALS.get(tf,"1d"); period=PERIODS.get(tf,"2y")
    df=_provider_frame(inst.data_symbol, interval, period, force_refresh=force_refresh)
    if df is None: return None
    if tf=="4H":
        df=df.resample("4h",origin="start_day").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()
    if as_of is not None:
        cutoff=pd.Timestamp(as_of)
        if cutoff.tzinfo is None: cutoff=cutoff.tz_localize("UTC")
        else: cutoff=cutoff.tz_convert("UTC")
        df=df[df.index<=cutoff]
    return df.tail(int(limit)) if len(df) else None


def prefetch_market_data(symbol: str, timeframes, max_workers: int = 7) -> None:
    """Warm the provider cache for a live MarketState build.

    Unique provider requests are keyed by (data symbol, interval, period), so 1H
    and 4H share one Yahoo 1h download. Failures are intentionally swallowed;
    the normal fetch path remains authoritative and will return None as before.
    """
    inst=get_instrument(symbol)
    requests=[]
    seen=set()
    for timeframe in timeframes:
        tf=str(timeframe)
        interval=INTERVALS.get(tf,"1d"); period=PERIODS.get(tf,"2y")
        key=(inst.data_symbol, interval, period)
        if key in seen: continue
        seen.add(key); requests.append(key)

    if not requests: return
    workers=max(1,min(int(max_workers),len(requests)))
    with ThreadPoolExecutor(max_workers=workers,thread_name_prefix="tp-market-prefetch") as pool:
        futures=[pool.submit(_provider_frame,*req) for req in requests]
        for future in as_completed(futures):
            try: future.result()
            except Exception: pass
