from __future__ import annotations
import pandas as pd
from v4_market_warehouse import normalize_candles

TF_SECONDS={"1m":60,"5m":300,"15m":900,"30m":1800,"1H":3600,"4H":14400,"D":86400,"W":604800}

def audit_frame(raw, timeframe):
    if raw is None or len(raw)==0:
        return {"rows":0,"duplicates":0,"bad_ohlc":0,"gap_count":0,"first_ts":None,"last_ts":None,"gaps":[]}
    x=raw.copy()
    if "timestamp" in x.columns:
        idx=pd.to_datetime(x["timestamp"],utc=True)
    else:
        idx=pd.to_datetime(x.index,utc=True)
    duplicates=int(idx.duplicated().sum())
    cols={str(c).lower():c for c in x.columns}
    bad=0
    if all(k in cols for k in ("open","high","low","close")):
        o=pd.to_numeric(x[cols["open"]],errors="coerce")
        h=pd.to_numeric(x[cols["high"]],errors="coerce")
        l=pd.to_numeric(x[cols["low"]],errors="coerce")
        c=pd.to_numeric(x[cols["close"]],errors="coerce")
        bad=int(((h < pd.concat([o,c,l],axis=1).max(axis=1)) |
                 (l > pd.concat([o,c,h],axis=1).min(axis=1))).sum())
    n=normalize_candles(raw)
    gaps=[]
    seconds=TF_SECONDS.get(timeframe)
    if seconds and len(n)>1:
        delta=n.index.to_series().diff().dt.total_seconds()
        # Futures have scheduled closures; only flag unusually large holes.
        threshold=seconds*3 if timeframe not in ("D","W") else seconds*4
        for ts,d in delta[delta>threshold].items():
            gaps.append({"ending_at":ts.isoformat(),"seconds":int(d)})
    return {"rows":len(n),"duplicates":duplicates,"bad_ohlc":bad,"gap_count":len(gaps),
            "first_ts":None if n.empty else n.index[0].isoformat(),
            "last_ts":None if n.empty else n.index[-1].isoformat(),"gaps":gaps[:250]}
