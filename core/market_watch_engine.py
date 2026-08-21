"""
The Trading Pulse - Lightweight Market Watch Engine V2.8

Purpose:
- Fetch a compact Yahoo Finance snapshot for the eight curated futures markets.
- Keep this separate from MarketState. Only GC currently has the validated
  deterministic Trading Pulse analysis/storage pipeline.
- Never create zones, setup grades, trade readiness, entries, stops, targets,
  or probabilities for watch-only symbols.

This module is intentionally read-only and database-free.
"""

from __future__ import annotations

from typing import Iterable
import math

import yfinance as yf


MARKETS = {
    "GC":  {"name": "Gold",         "data_symbol": "GC=F"},
    "SI":  {"name": "Silver",       "data_symbol": "SI=F"},
    "ES":  {"name": "S&P 500",      "data_symbol": "ES=F"},
    "NQ":  {"name": "Nasdaq 100",   "data_symbol": "NQ=F"},
    "YM":  {"name": "Dow",          "data_symbol": "YM=F"},
    "RTY": {"name": "Russell 2000", "data_symbol": "RTY=F"},
    "CL":  {"name": "Crude Oil",    "data_symbol": "CL=F"},
    "NG":  {"name": "Natural Gas",  "data_symbol": "NG=F"},
}


def _finite(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except Exception:
        return None


def _one_snapshot(root: str) -> dict:
    meta = MARKETS[root]
    ticker = yf.Ticker(meta["data_symbol"])

    # Five trading days at 30m gives the small card enough context to be useful.
    hist = ticker.history(period="5d", interval="30m", auto_adjust=False)
    if hist is None or hist.empty:
        hist = ticker.history(period="5d", interval="1h", auto_adjust=False)

    if hist is None or hist.empty or "Close" not in hist.columns:
        return {
            "root_symbol": root,
            "name": meta["name"],
            "data_symbol": meta["data_symbol"],
            "price": None,
            "previous_close": None,
            "change": None,
            "change_pct": None,
            "sparkline": [],
            "timestamp": None,
        }

    close = hist["Close"].dropna()
    if close.empty:
        return {
            "root_symbol": root,
            "name": meta["name"],
            "data_symbol": meta["data_symbol"],
            "price": None,
            "previous_close": None,
            "change": None,
            "change_pct": None,
            "sparkline": [],
            "timestamp": None,
        }

    price = _finite(close.iloc[-1])

    daily = ticker.history(period="5d", interval="1d", auto_adjust=False)
    daily_close = daily["Close"].dropna() if daily is not None and not daily.empty and "Close" in daily.columns else close
    previous_close = _finite(daily_close.iloc[-2]) if len(daily_close) >= 2 else _finite(close.iloc[0])

    change = None
    change_pct = None
    if price is not None and previous_close not in (None, 0):
        change = price - previous_close
        change_pct = change / previous_close * 100.0

    spark = [_finite(v) for v in close.tail(80).tolist()]
    spark = [v for v in spark if v is not None]

    timestamp = None
    try:
        timestamp = close.index[-1].isoformat()
    except Exception:
        pass

    return {
        "root_symbol": root,
        "name": meta["name"],
        "data_symbol": meta["data_symbol"],
        "price": price,
        "previous_close": previous_close,
        "change": change,
        "change_pct": change_pct,
        "sparkline": spark,
        "timestamp": timestamp,
    }


def fetch_market_watch(symbols: Iterable[str] | None = None) -> dict[str, dict]:
    requested = [str(s).upper() for s in (symbols or MARKETS.keys())]
    result = {}
    for root in requested:
        if root not in MARKETS:
            continue
        try:
            result[root] = _one_snapshot(root)
        except Exception as exc:
            meta = MARKETS[root]
            result[root] = {
                "root_symbol": root,
                "name": meta["name"],
                "data_symbol": meta["data_symbol"],
                "price": None,
                "previous_close": None,
                "change": None,
                "change_pct": None,
                "sparkline": [],
                "timestamp": None,
                "error": str(exc),
            }
    return result
