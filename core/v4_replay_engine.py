from __future__ import annotations
import pandas as pd
from v4_point_in_time import PointInTimeReader

class ReplayClock:
    """Chronological replay. Callback receives only candles at/before the replay timestamp."""
    def __init__(self,warehouse_path="research_data/v4/market_warehouse.db"):
        self.reader=PointInTimeReader(warehouse_path)
    def run(self,symbol,timeframe,start=None,end=None,warmup=250,step=1,callback=None):
        full=self.reader.wh.read(symbol,timeframe,start=start,end=end)
        results=[]
        if len(full)<=warmup: return results
        for i in range(warmup,len(full),max(1,int(step))):
            as_of=full.index[i]
            frame=self.reader.candles(symbol,timeframe,as_of,limit=warmup+1)
            if len(frame) and frame.index.max()>as_of: raise AssertionError("future candle exposed")
            if callback: results.append(callback(symbol,timeframe,as_of,frame))
        return results
