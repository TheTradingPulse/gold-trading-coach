"""Canonical, mutually-exclusive first-touch classification for V4 evidence.

This module is deliberately independent of the dashboard and database writers.
It can reclassify existing rows from persisted relative bar ordering and is also
the contract new replays should write going forward.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class FirstTouch:
    entered: bool
    primary_class: str
    stretch_class: str
    primary_before_stop: bool
    stretch_before_stop: bool
    same_bar_ambiguous: bool
    entry_bar: int | None
    primary_bar: int | None
    stretch_bar: int | None
    stop_bar: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _target_class(hit: bool, target_bar: int | None, stop_hit: bool,
                  stop_bar: int | None, ambiguous: bool) -> tuple[str, bool]:
    if not hit:
        return ("STOP_FIRST" if stop_hit else "UNRESOLVED"), False
    if not stop_hit:
        return "TARGET_FIRST", True
    if target_bar is not None and stop_bar is not None:
        if target_bar < stop_bar:
            return "TARGET_FIRST_THEN_STOP", True
        if target_bar > stop_bar:
            return "STOP_FIRST", False
        return "SAME_BAR_AMBIGUOUS", False
    if ambiguous:
        return "SAME_BAR_AMBIGUOUS", False
    return "ORDER_UNKNOWN", False


def classify_first_touch(row: Mapping[str, Any], outcome: Mapping[str, Any] | None = None) -> FirstTouch:
    """Classify a stored evidence row without assuming OHLC intrabar ordering.

    `bars_to_outcome` is the stop bar when stop_hit is true because the existing
    V4 outcome engine terminates on that stop. Same-bar target/stop is always
    conservative: it is never counted as target-first.
    """
    o = outcome or {}
    get = lambda key, default=None: row.get(key, o.get(key, default))
    entered = bool(get("entered", False))
    entry_bar = _int(get("bars_to_entry"))
    primary_bar = _int(get("bars_to_primary"))
    stretch_bar = _int(get("bars_to_stretch"))
    stop_hit = bool(get("stop_hit", False))
    stop_bar = _int(get("bars_to_outcome")) if stop_hit else None
    primary_hit = bool(get("primary_hit", False))
    stretch_hit = bool(get("stretch_hit", False))
    ambiguous = bool(get("same_bar_ambiguous", False))
    if not entered:
        return FirstTouch(False, "NOT_ENTERED", "NOT_ENTERED", False, False,
                          False, entry_bar, None, None, None)
    pc, pb = _target_class(primary_hit, primary_bar, stop_hit, stop_bar, ambiguous)
    sc, sb = _target_class(stretch_hit, stretch_bar, stop_hit, stop_bar, ambiguous)
    return FirstTouch(True, pc, sc, pb, sb,
                      pc == "SAME_BAR_AMBIGUOUS" or sc == "SAME_BAR_AMBIGUOUS",
                      entry_bar, primary_bar, stretch_bar, stop_bar)
