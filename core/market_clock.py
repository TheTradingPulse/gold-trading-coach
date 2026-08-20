"""The Trading Pulse - Historical Market Clock V2.8A.

Provides one explicit time boundary for LIVE and REPLAY analysis.
All replay-aware data access must use ``clock.cutoff``.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
import pandas as pd

VALID_CLOCK_MODES = {"LIVE", "REPLAY"}

def normalize_timestamp(value) -> Optional[pd.Timestamp]:
    if value is None:
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts

@dataclass(frozen=True)
class MarketClock:
    mode: str = "LIVE"
    replay_timestamp: Optional[Any] = None

    def __post_init__(self):
        mode = str(self.mode).upper().strip()
        if mode not in VALID_CLOCK_MODES:
            raise ValueError(f"Invalid clock mode {self.mode!r}; expected LIVE or REPLAY")
        object.__setattr__(self, "mode", mode)
        ts = normalize_timestamp(self.replay_timestamp)
        if mode == "REPLAY" and ts is None:
            raise ValueError("REPLAY mode requires replay_timestamp")
        if mode == "LIVE" and ts is not None:
            raise ValueError("LIVE mode cannot contain replay_timestamp")
        object.__setattr__(self, "replay_timestamp", ts)

    @property
    def is_replay(self) -> bool:
        return self.mode == "REPLAY"

    @property
    def cutoff(self) -> Optional[pd.Timestamp]:
        return self.replay_timestamp if self.is_replay else None

    @property
    def cutoff_iso(self) -> Optional[str]:
        return self.cutoff.isoformat() if self.cutoff is not None else None

    def to_dict(self) -> dict:
        return {"mode": self.mode, "is_replay": self.is_replay, "cutoff": self.cutoff_iso}

def live_clock() -> MarketClock:
    return MarketClock(mode="LIVE")

def replay_clock(timestamp) -> MarketClock:
    return MarketClock(mode="REPLAY", replay_timestamp=timestamp)
