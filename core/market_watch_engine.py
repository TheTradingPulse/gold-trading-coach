"""The Trading Pulse - Canonical Market Watch Engine V3.3G.

Market Watch consumes the same load_market_data boundary used by MarketState and charts.
There is no independent watch-only price feed.
"""
from __future__ import annotations
from typing import Iterable
import math
from market_state_builder import load_market_data, get_latest_market_price
from instruments import get_instrument

MARKETS = {s: {"name": get_instrument(s).name.replace(" Futures", ""), "data_symbol": get_instrument(s).data_symbol}
           for s in ("GC","SI","ES","NQ","YM","RTY","CL","NG")}

def _finite(value):
    try:
        value=float(value); return value if math.isfinite(value) else None
    except Exception: return None

def _one_snapshot(root: str) -> dict:
    meta=MARKETS[root]
    price, timestamp, price_timeframe = get_latest_market_price(symbol=root)
    price=_finite(price)
    daily=load_market_data("D", limit=3, symbol=root)
    previous_close=None
    if daily is not None and not daily.empty and "close" in daily.columns:
        closes=daily["close"].dropna()
        if len(closes)>=2: previous_close=_finite(closes.iloc[-2])
        elif len(closes)==1: previous_close=_finite(closes.iloc[-1])
    change=change_pct=None
    if price is not None and previous_close not in (None,0):
        change=price-previous_close; change_pct=change/previous_close*100.0
    return {"root_symbol":root,"name":meta["name"],"data_symbol":meta["data_symbol"],
            "price":price,"previous_close":previous_close,"change":change,"change_pct":change_pct,
            "sparkline":[],"timestamp":timestamp.isoformat() if hasattr(timestamp,"isoformat") else timestamp,
            "price_timeframe":price_timeframe,"source":"CANONICAL_MARKET_DATA"}

def fetch_market_watch(symbols: Iterable[str] | None=None) -> dict[str,dict]:
    requested=[str(s).upper() for s in (symbols or MARKETS.keys())]; result={}
    for root in requested:
        if root not in MARKETS: continue
        try: result[root]=_one_snapshot(root)
        except Exception as exc:
            meta=MARKETS[root]; result[root]={"root_symbol":root,"name":meta["name"],"data_symbol":meta["data_symbol"],
                "price":None,"previous_close":None,"change":None,"change_pct":None,"sparkline":[],"timestamp":None,
                "source":"CANONICAL_MARKET_DATA","error":str(exc)}
    return result
