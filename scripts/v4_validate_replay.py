import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_market_warehouse import MarketWarehouse
from v4_canonical_replay import UNIVERSE,WarehouseMarketStateAdapter
wh=MarketWarehouse();ad=WarehouseMarketStateAdapter()
fail=[]
for s in UNIVERSE:
    cov=[x for x in wh.coverage() if x["symbol"]==s and x["timeframe"]=="15m"]
    if not cov: print("[SKIP]",s,"no 15m data");continue
    df=wh.read(s,"15m",limit=400)
    if len(df)<260: print("[SKIP]",s,"insufficient bars");continue
    ts=df.index[-50]
    try:
        st,c=ad.candidates(s,ts)
        print("[PASS]",s,ts,"candidates",len(c))
    except Exception as e:
        print("[FAIL]",s,e);fail.append((s,str(e)))
if fail: raise SystemExit(1)
print("MULTI-MARKET CANONICAL REPLAY VALIDATION PASS")
