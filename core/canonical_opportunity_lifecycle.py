"""Fail-closed lifecycle classification for canonical professional zones."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

import pandas as pd

LIFECYCLE_VERSION = "TP_CANONICAL_LIFECYCLE_1"
ACTIVE_STATES = {"TRIGGERED_RECENT", "ACTIVE_RISK", "MANAGING"}
TERMINAL_STATES = {"RESOLVED_STOP", "RESOLVED_TARGET", "SAME_BAR_AMBIGUOUS", "EXPIRED"}


@dataclass(frozen=True)
class LifecycleResult:
    lifecycle_version: str
    state: str
    dashboard_eligible: bool
    execution_verified: bool
    target_rr: float
    age_bars: int
    max_verified_r: float
    current_r: float
    first_stop_ts: str | None
    first_target_ts: str | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def _closed_bars(bars: pd.DataFrame, as_of: Any | None) -> pd.DataFrame:
    x = bars.copy()
    if not isinstance(x.index, pd.DatetimeIndex):
        for name in ("timestamp", "ts", "datetime"):
            if name in x.columns:
                x = x.set_index(name)
                break
    x.index = pd.to_datetime(x.index, utc=True)
    x = x.sort_index()
    if as_of is not None:
        x = x.loc[x.index <= _utc(as_of)]
    required = {"high", "low", "close"}
    missing = required.difference(x.columns)
    if missing:
        raise ValueError(f"bars missing required columns: {sorted(missing)}")
    return x


def classify_zone(
    zone: Mapping[str, Any],
    bars: pd.DataFrame,
    *,
    as_of: Any | None = None,
    target_rr: float = 5.0,
    recent_bars: int = 2,
    max_active_bars: int = 576,
) -> dict[str, Any]:
    """Classify a triggered zone using only closed bars.

    Same-bar target/stop ordering is unknowable at this resolution and is
    deliberately excluded from live display. Expiration is an operational
    guardrail, not a claim of statistical edge.
    """
    direction = str(zone["direction"]).upper()
    if direction not in {"LONG", "SHORT"}:
        raise ValueError("direction must be LONG or SHORT")
    entry, stop, risk = float(zone["entry"]), float(zone["stop"]), float(zone["risk"])
    if risk <= 0:
        raise ValueError("risk must be positive")
    target_rr = float(target_rr)
    if target_rr <= 0:
        raise ValueError("target_rr must be positive")

    x = _closed_bars(bars, as_of)
    start = _utc(zone["entry_ts"])
    x = x.loc[x.index >= start]
    if x.empty:
        return LifecycleResult(LIFECYCLE_VERSION, "TRIGGERED_RECENT", False, False,
            target_rr, 0, 0.0, 0.0, None, None, "no closed bar at or after trigger").to_dict()

    first_stop = first_target = None
    max_r = 0.0
    for ts, bar in x.iterrows():
        if direction == "LONG":
            stop_hit = float(bar.low) <= stop
            target_hit = float(bar.high) >= entry + target_rr * risk
            favorable = (float(bar.high) - entry) / risk
        else:
            stop_hit = float(bar.high) >= stop
            target_hit = float(bar.low) <= entry - target_rr * risk
            favorable = (entry - float(bar.low)) / risk
        max_r = max(max_r, favorable)
        if stop_hit and target_hit:
            return LifecycleResult(LIFECYCLE_VERSION, "SAME_BAR_AMBIGUOUS", False, False,
                target_rr, len(x), round(max(0.0, max_r), 4), 0.0, str(ts), str(ts),
                "stop and target touched in the same closed bar; ordering unknown").to_dict()
        if target_hit:
            first_target = ts
            return LifecycleResult(LIFECYCLE_VERSION, "RESOLVED_TARGET", False, True,
                target_rr, len(x), round(max_r, 4), target_rr, None, str(ts),
                "target touched before stop on a separate closed bar").to_dict()
        if stop_hit:
            first_stop = ts
            return LifecycleResult(LIFECYCLE_VERSION, "RESOLVED_STOP", False, True,
                target_rr, len(x), round(max(0.0, max_r), 4), -1.0, str(ts), None,
                "stop touched before target on a separate closed bar").to_dict()

    close = float(x.iloc[-1].close)
    current_r = (close - entry) / risk if direction == "LONG" else (entry - close) / risk
    age = len(x)
    if age > max_active_bars:
        state, eligible, reason = "EXPIRED", False, "provisional maximum active-bar age exceeded"
    elif max_r >= 1.0:
        state, eligible, reason = "MANAGING", True, "at least 1R favorable excursion; final target unresolved"
    elif age <= recent_bars:
        state, eligible, reason = "TRIGGERED_RECENT", True, "trigger occurred within recent closed bars"
    else:
        state, eligible, reason = "ACTIVE_RISK", True, "triggered; neither stop nor target resolved"
    return LifecycleResult(LIFECYCLE_VERSION, state, eligible, True, target_rr, age,
        round(max(0.0, max_r), 4), round(current_r, 4),
        str(first_stop) if first_stop else None, str(first_target) if first_target else None, reason).to_dict()


def classify_zones(zones: pd.DataFrame, bars: pd.DataFrame, **kwargs: Any) -> pd.DataFrame:
    rows = []
    for _, zone in zones.iterrows():
        row = zone.to_dict()
        row.update(classify_zone(row, bars, **kwargs))
        rows.append(row)
    return pd.DataFrame(rows)
