from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional

DEFAULT_PRIMARY_R = 3.0
DEFAULT_STRETCH_R = 5.0
DEFAULT_STOP_R = -1.0

@dataclass(frozen=True)
class ResearchTargetPolicy:
    primary_r: float = DEFAULT_PRIMARY_R
    stretch_r: float = DEFAULT_STRETCH_R
    stop_r: float = DEFAULT_STOP_R

    def validate(self) -> "ResearchTargetPolicy":
        if self.primary_r <= 0:
            raise ValueError("primary_r must be > 0")
        if self.stretch_r <= self.primary_r:
            raise ValueError("stretch_r must be greater than primary_r")
        if self.stop_r >= 0:
            raise ValueError("stop_r must be negative")
        return self

DEFAULT_POLICY = ResearchTargetPolicy().validate()

def _f(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def planned_levels(candidate: Dict[str, Any], policy: ResearchTargetPolicy = DEFAULT_POLICY) -> Dict[str, float]:
    entry = _f(candidate.get("entry"))
    stop = _f(candidate.get("stop"))
    side = str(candidate.get("direction", "")).upper()
    if entry is None or stop is None or side not in {"LONG", "SHORT"}:
        raise ValueError("candidate requires direction, entry, and stop")
    risk = abs(entry - stop)
    if risk <= 0:
        raise ValueError("candidate risk must be > 0")
    sign = 1.0 if side == "LONG" else -1.0
    return {
        "entry": entry,
        "stop": stop,
        "risk_points": risk,
        "primary_r": policy.primary_r,
        "stretch_r": policy.stretch_r,
        "primary_target": entry + sign * risk * policy.primary_r,
        "stretch_target": entry + sign * risk * policy.stretch_r,
    }
