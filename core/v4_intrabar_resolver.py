"""One-minute first-touch resolver for ambiguous higher-timeframe outcomes."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class IntrabarResolution:
    result: str
    entered: bool
    entry_time: str | None
    target_time: str | None
    stop_time: str | None
    ambiguous_time: str | None

    def to_dict(self): return asdict(self)


def _touch(side: str, lo: float, hi: float, entry: float, stop: float, target: float):
    if side == "LONG":
        return lo <= entry <= hi, lo <= stop, hi >= target
    return lo <= entry <= hi, hi >= stop, lo <= target


def resolve_minutes(minutes: Any, side: str, entry: float, stop: float, target: float,
                    already_entered: bool = True) -> IntrabarResolution:
    side = str(side).upper()
    if side not in {"LONG", "SHORT"}: raise ValueError("side must be LONG or SHORT")
    active=bool(already_entered); entry_time=None
    for ts,row in minutes.iterrows():
        lo=float(row["low"]);hi=float(row["high"])
        entry_touch,stop_touch,target_touch=_touch(side,lo,hi,entry,stop,target)
        if not active:
            if not entry_touch: continue
            active=True;entry_time=str(ts)
        if stop_touch and target_touch:
            return IntrabarResolution("SAME_MINUTE_AMBIGUOUS",True,entry_time,None,None,str(ts))
        if stop_touch:
            return IntrabarResolution("STOP_FIRST",True,entry_time,None,str(ts),None)
        if target_touch:
            return IntrabarResolution("TARGET_FIRST",True,entry_time,str(ts),None,None)
    return IntrabarResolution("UNRESOLVED",active,entry_time,None,None,None)
