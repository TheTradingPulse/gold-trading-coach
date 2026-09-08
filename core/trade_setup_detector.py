"""Causal detector for the three approved visual setup families.

All bar indices are interpreted as *bar-close availability timestamps*.  The
detector never receives bars later than the decision it is evaluating.
"""
from __future__ import annotations

from hashlib import sha256

import numpy as np
import pandas as pd


DETECTOR_VERSION = "TP_THREE_SETUP_DETECTOR_1"
GC_MGC_DOLLARS_PER_POINT = 10.0


def _prepare(frame: pd.DataFrame) -> pd.DataFrame:
    x = frame.copy().sort_index()
    x.columns = [str(c).lower() for c in x.columns]
    needed = {"open", "high", "low", "close"}
    if not needed.issubset(x.columns):
        raise ValueError(f"OHLC frame missing {sorted(needed - set(x.columns))}")
    x = x.loc[~x.index.duplicated(keep="last")]
    previous = x.close.shift(1)
    true_range = pd.concat(
        [(x.high - x.low), (x.high - previous).abs(), (x.low - previous).abs()], axis=1
    ).max(axis=1)
    x["atr"] = true_range.rolling(14, min_periods=10).mean()
    x["ema20"] = x.close.ewm(span=20, adjust=False).mean()
    x["ema50"] = x.close.ewm(span=50, adjust=False).mean()
    x["prior_high_8"] = x.high.shift(1).rolling(8, min_periods=6).max()
    x["prior_low_8"] = x.low.shift(1).rolling(8, min_periods=6).min()
    x["prior_high_24"] = x.high.shift(1).rolling(24, min_periods=16).max()
    x["prior_low_24"] = x.low.shift(1).rolling(24, min_periods=16).min()
    return x


def _trend_4h(known: pd.DataFrame) -> str:
    if len(known) < 20:
        return "NO_DATA"
    last = known.iloc[-1]
    # Recent structural breaks override lagging averages.
    prior_high = known.high.iloc[-11:-1].max()
    prior_low = known.low.iloc[-11:-1].min()
    if last.close > prior_high:
        return "BULLISH"
    if last.close < prior_low:
        return "BEARISH"
    slope = known.ema20.iloc[-1] - known.ema20.iloc[-4]
    if last.close > last.ema20 > last.ema50 and slope > 0:
        return "BULLISH"
    if last.close < last.ema20 < last.ema50 and slope < 0:
        return "BEARISH"
    return "NEUTRAL"


def _id(family: str, direction: str, ts: pd.Timestamp, entry: float) -> str:
    raw = f"GC|{family}|{direction}|{ts.isoformat()}|{entry:.4f}"
    return sha256(raw.encode()).hexdigest()[:20]


def _candidate(family, direction, ts, row, trend, stop, room_level, **flags):
    entry = float(row.close)
    risk = abs(entry - stop)
    room_r = abs(room_level - entry) / risk if risk > 0 else 0.0
    return {
        "candidate_id": _id(family, direction, ts, entry),
        "detector_version": DETECTOR_VERSION,
        "setup_family": family,
        "direction": direction,
        "decision_ts": ts.isoformat(),
        "entry": entry,
        "stop": float(stop),
        "risk_dollars": risk * GC_MGC_DOLLARS_PER_POINT,
        "room_r": room_r,
        "trend_4h": trend,
        "location_valid": True,
        "displacement": True,
        "confirmation_close": True,
        "structure_break_15m": True,
        "pullback_valid": False,
        "breakout_confirmed": False,
        "retest_confirmed": False,
        "liquidity_sweep": False,
        "reclaim_confirmed": False,
        "opposing_structure_clear": room_r >= 3.0,
        **flags,
    }


def detect_trade_setups(m15: pd.DataFrame, h4: pd.DataFrame) -> pd.DataFrame:
    """Return frozen candidate rows; outcome data is intentionally absent."""
    m = _prepare(m15)
    h = _prepare(h4)
    rows: list[dict] = []
    for i in range(30, len(m)):
        now = m.index[i]
        row = m.iloc[i]
        if not np.isfinite(row.atr) or row.atr <= 0:
            continue
        known_4h = h[h.index <= now]
        trend = _trend_4h(known_4h)
        recent = m.iloc[max(0, i - 7):i]
        body = abs(row.close - row.open)
        bullish_displacement = row.close > row.open and body >= 0.5 * row.atr
        bearish_displacement = row.close < row.open and body >= 0.5 * row.atr
        buffer = max(0.2, 0.15 * row.atr)
        room_high = float(known_4h.high.tail(50).max()) if len(known_4h) else float(row.prior_high_24)
        room_low = float(known_4h.low.tail(50).min()) if len(known_4h) else float(row.prior_low_24)

        # 1) Pullback into value, then a close through prior local structure.
        pullback_long = bool((recent.low <= recent.ema20).any() and recent.low.min() > row.prior_low_24)
        pullback_short = bool((recent.high >= recent.ema20).any() and recent.high.max() < row.prior_high_24)
        if trend == "BULLISH" and pullback_long and bullish_displacement and row.close > row.prior_high_8:
            stop = float(recent.low.min() - buffer)
            rows.append(_candidate("TREND_CONTINUATION", "LONG", now, row, trend, stop, room_high,
                                   pullback_valid=True))
        if trend == "BEARISH" and pullback_short and bearish_displacement and row.close < row.prior_low_8:
            stop = float(recent.high.max() + buffer)
            rows.append(_candidate("TREND_CONTINUATION", "SHORT", now, row, trend, stop, room_low,
                                   pullback_valid=True))

        # 2) A prior close breaks a 24-bar boundary; price retests that exact
        # boundary and the current candle confirms away from it.
        for j in range(max(24, i - 8), i):
            breakout = m.iloc[j]
            between = m.iloc[j + 1:i + 1]
            if (breakout.close > breakout.prior_high_24 and
                    (between.low <= breakout.prior_high_24 + 0.15 * row.atr).any() and
                    row.low <= breakout.prior_high_24 + 0.15 * row.atr and
                    bullish_displacement and row.close > breakout.prior_high_24):
                stop = float(min(between.low.min(), breakout.prior_high_24) - buffer)
                rows.append(_candidate("BREAKOUT_RETEST", "LONG", now, row, trend, stop, room_high,
                                       breakout_confirmed=True, retest_confirmed=True))
                break
            if (breakout.close < breakout.prior_low_24 and
                    (between.high >= breakout.prior_low_24 - 0.15 * row.atr).any() and
                    row.high >= breakout.prior_low_24 - 0.15 * row.atr and
                    bearish_displacement and row.close < breakout.prior_low_24):
                stop = float(max(between.high.max(), breakout.prior_low_24) + buffer)
                rows.append(_candidate("BREAKOUT_RETEST", "SHORT", now, row, trend, stop, room_low,
                                       breakout_confirmed=True, retest_confirmed=True))
                break

        # 3) Sweep an established extreme, reclaim it, then close through the
        # opposing six-bar structure. This is the only countertrend family.
        sweep_window = m.iloc[max(0, i - 6):i]
        long_sweep = sweep_window[sweep_window.low < sweep_window.prior_low_24]
        short_sweep = sweep_window[sweep_window.high > sweep_window.prior_high_24]
        if len(long_sweep) and row.close > row.prior_high_8 and bullish_displacement:
            swept = long_sweep.iloc[-1]
            if swept.close > swept.prior_low_24:
                stop = float(long_sweep.low.min() - buffer)
                rows.append(_candidate("LIQUIDITY_SWEEP_REVERSAL", "LONG", now, row, trend, stop, room_high,
                                       liquidity_sweep=True, reclaim_confirmed=True))
        if len(short_sweep) and row.close < row.prior_low_8 and bearish_displacement:
            swept = short_sweep.iloc[-1]
            if swept.close < swept.prior_high_24:
                stop = float(short_sweep.high.max() + buffer)
                rows.append(_candidate("LIQUIDITY_SWEEP_REVERSAL", "SHORT", now, row, trend, stop, room_low,
                                       liquidity_sweep=True, reclaim_confirmed=True))

    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows).drop_duplicates("candidate_id")
    return result.sort_values(["decision_ts", "setup_family"]).reset_index(drop=True)
