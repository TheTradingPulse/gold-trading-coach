from __future__ import annotations
import math, json
import pandas as pd

def _num(v):
    try:
        f=float(v); return None if math.isnan(f) else f
    except Exception: return None

def build_chart_packet(symbol,timeframes,market_state_payload=None,selected_setup=None,as_of=None):
    packet={"schema":"tradingpulse.chart_intelligence.v1","symbol":symbol.upper(),
            "as_of":None if as_of is None else str(as_of),"timeframes":{},
            "market_state":market_state_payload or {},"selected_setup":selected_setup or {}}
    for tf,df in timeframes.items():
        if df is None or len(df)==0:
            packet["timeframes"][tf]={"bars":0}; continue
        x=df.sort_index()
        close=x["close"].astype(float)
        last=x.iloc[-1]
        ret=(close.iloc[-1]/close.iloc[-2]-1.0) if len(close)>1 and close.iloc[-2] else None
        packet["timeframes"][tf]={
            "bars":len(x),"first":x.index[0].isoformat(),"last":x.index[-1].isoformat(),
            "open":_num(last["open"]),"high":_num(last["high"]),"low":_num(last["low"]),
            "close":_num(last["close"]),"volume":_num(last.get("volume",0)),
            "last_bar_return":ret,
            "range_high":_num(x["high"].max()),"range_low":_num(x["low"].min()),
            "ema20":_num(close.ewm(span=20,adjust=False).mean().iloc[-1]) if len(close)>=20 else None,
            "ema50":_num(close.ewm(span=50,adjust=False).mean().iloc[-1]) if len(close)>=50 else None,
        }
    return packet
