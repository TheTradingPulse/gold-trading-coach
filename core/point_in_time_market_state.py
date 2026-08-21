"""
Trading Pulse V3.1B
Point-in-Time MarketState Replay Bridge

Historical research must never fall through to the live/reference
market-data provider.

The canonical production MarketState builder obtains candles through
market_state_builder.load_market_data(). During replay we temporarily
replace that boundary with caller-supplied historical frames.

The production dependency is ALWAYS restored in finally.
"""

from __future__ import annotations

from typing import Mapping

import pandas as pd
import market_state_builder as _msb


ENGINE_VERSION = "3.1B"


def _empty_market_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["open", "high", "low", "close", "volume"]
    )


def build_market_state_from_frames(
    symbol: str,
    frames: Mapping[str, pd.DataFrame],
    as_of=None,
):
    """
    Build the production MarketState using only historical frames supplied
    by the replay/research engine.

    No database, Yahoo, broker, or live-provider fallback is allowed.
    """

    root_symbol = str(symbol).strip().upper()

    supplied = {}

    for timeframe, frame in frames.items():

        tf = str(timeframe)

        if frame is None:
            supplied[tf] = _empty_market_frame()
            continue

        historical = frame.copy().sort_index()

        # Normalize provider OHLCV into canonical Trading Pulse schema.
        historical.columns = [
            str(col).strip().lower()
            for col in historical.columns
        ]

        required_ohlcv = {"open", "high", "low", "close", "volume"}
        missing_ohlcv = required_ohlcv.difference(historical.columns)

        if missing_ohlcv:
            raise ValueError(
                f"Historical frame {tf} missing OHLCV columns: {sorted(missing_ohlcv)}"
            )

        if as_of is not None and isinstance(
            historical.index,
            pd.DatetimeIndex,
        ):
            timestamp = pd.Timestamp(as_of)

            if historical.index.tz is not None and timestamp.tzinfo is None:
                timestamp = timestamp.tz_localize(historical.index.tz)

            elif historical.index.tz is None and timestamp.tzinfo is not None:
                timestamp = timestamp.tz_localize(None)

            historical = historical.loc[
                historical.index <= timestamp
            ]

        supplied[tf] = historical

    original_load_market_data = _msb.load_market_data

    def point_in_time_load_market_data(
        timeframe: str,
        limit: int = 500,
        as_of=None,
        symbol="GC",
        *args,
        **kwargs,
    ):
        """
        Historical replacement for production load_market_data().

        IMPORTANT:
        Missing replay timeframes return EMPTY data rather than falling
        through to production/live/reference sources.
        """

        requested_symbol = str(symbol).strip().upper()
        requested_timeframe = str(timeframe)

        if requested_symbol != root_symbol:
            return _empty_market_frame()

        frame = supplied.get(requested_timeframe)

        if frame is None or frame.empty:
            return _empty_market_frame()

        historical = frame

        if as_of is not None and isinstance(
            historical.index,
            pd.DatetimeIndex,
        ):
            timestamp = pd.Timestamp(as_of)

            if historical.index.tz is not None and timestamp.tzinfo is None:
                timestamp = timestamp.tz_localize(historical.index.tz)

            elif historical.index.tz is None and timestamp.tzinfo is not None:
                timestamp = timestamp.tz_localize(None)

            historical = historical.loc[
                historical.index <= timestamp
            ]

        if limit is not None:
            historical = historical.tail(int(limit))

        return historical.copy()

    _msb.load_market_data = point_in_time_load_market_data

    try:

        # build_market_state() remains the REAL production MarketState
        # architecture. Only its candle source is replaced.
        return _msb.build_market_state(
            symbol=root_symbol,
            as_of=as_of,
        )

    finally:

        # Critical safety requirement:
        # never leave production MarketState attached to replay data.
        _msb.load_market_data = original_load_market_data

