from __future__ import annotations
import pandas as pd
from v4_market_warehouse import MarketWarehouse

def _utc(value):
    ts=pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")

class PointInTimeReader:
    def __init__(self,path="research_data/v4/market_warehouse.db"):
        self.wh=MarketWarehouse(path)
    def candles(self,symbol,timeframe,as_of,limit=500,provider=None):
        cutoff=_utc(as_of)
        df=self.wh.read(symbol,timeframe,as_of=cutoff,limit=limit,provider=provider)
        if len(df) and df.index.max()>cutoff:
            raise AssertionError("LOOK-AHEAD VIOLATION")
        return df
    def multi_timeframe(self,symbol,as_of,timeframes=("5m","15m","1H","4H","D"),limit=500):
        return {tf:self.candles(symbol,tf,as_of,limit) for tf in timeframes}
