"""The Trading Pulse - Historical Replay / Event Engine V2.8C.

Walks the canonical MarketState through historical timestamps using the V2.8A
clock. Every state is generated with the same no-lookahead database boundary.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Callable, Iterable, Optional
import pandas as pd

from market_clock import replay_clock, normalize_timestamp
from setup_fingerprint import build_setup_fingerprint

@dataclass
class HistoricalEvent:
    event_timestamp: str
    fingerprint_id: str
    root_symbol: str
    setup_state: Optional[str]
    direction: Optional[str]
    market_bias: Optional[str]
    alignment_score: Optional[float]
    current_price: Optional[float]
    trade_ready: bool
    fingerprint: dict

    def to_dict(self):
        return asdict(self)

def build_historical_event(state, clock) -> HistoricalEvent:
    fp = build_setup_fingerprint(state, clock=clock)
    return HistoricalEvent(
        event_timestamp=fp["market_timestamp"],
        fingerprint_id=fp["fingerprint_id"],
        root_symbol=fp["root_symbol"],
        setup_state=fp["confirmation"]["setup_state"],
        direction=fp["confirmation"]["setup_direction"],
        market_bias=fp["market"]["market_bias"],
        alignment_score=fp["market"]["alignment_score"],
        current_price=fp["market"]["current_price"],
        trade_ready=fp["confirmation"]["setup_state"] == "TRADE_READY",
        fingerprint=fp,
    )

def replay_timestamps(start, end, step="15min") -> list[pd.Timestamp]:
    start_ts, end_ts = normalize_timestamp(start), normalize_timestamp(end)
    if start_ts is None or end_ts is None:
        raise ValueError("start and end are required")
    if end_ts < start_ts:
        raise ValueError("end must be >= start")
    return list(pd.date_range(start=start_ts, end=end_ts, freq=step))

def replay_market_states(
    build_state: Callable,
    symbol: str,
    timestamps: Iterable,
    *,
    event_filter: Optional[Callable[[HistoricalEvent], bool]] = None,
) -> list[HistoricalEvent]:
    events = []
    previous_id = None
    for ts in timestamps:
        clock = replay_clock(ts)
        state = build_state(symbol, clock=clock)
        if state.market_timestamp is None:
            continue
        event = build_historical_event(state, clock)
        # Do not store duplicate snapshots when a requested clock step lands
        # between actual candles and nothing observable changed.
        if event.fingerprint_id == previous_id:
            continue
        previous_id = event.fingerprint_id
        if event_filter is None or event_filter(event):
            events.append(event)
    return events
