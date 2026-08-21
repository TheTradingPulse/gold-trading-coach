"""Trading Pulse V3.0A multi-instrument reference-data adapter.
Yahoo data is development/reference data only and is never execution eligible.
"""
from __future__ import annotations
import pandas as pd
import yfinance as yf
from instruments import get_instrument

INTERVALS={"1m":"1m","5m":"5m","15m":"15m","1H":"1h","4H":"1h","D":"1d","W":"1wk","M":"1mo"}
PERIODS={"1m":"7d","5m":"60d","15m":"60d","1H":"730d","4H":"730d","D":"10y","W":"10y","M":"max"}

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

def fetch_market_data(symbol:str,timeframe:str,limit:int=500,as_of=None):
    inst=get_instrument(symbol); tf=str(timeframe)
    interval=INTERVALS.get(tf,"1d"); period=PERIODS.get(tf,"2y")
    try: df=yf.download(inst.data_symbol,period=period,interval=interval,progress=False,auto_adjust=False)
    except Exception: return None
    df=_normalize(df)
    if df is None: return None
    if tf=="4H":
        df=df.resample("4h",origin="start_day").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()
    if as_of is not None:
        cutoff=pd.Timestamp(as_of)
        if cutoff.tzinfo is None: cutoff=cutoff.tz_localize("UTC")
        else: cutoff=cutoff.tz_convert("UTC")
        df=df[df.index<=cutoff]
    return df.tail(int(limit)) if len(df) else None
