"""
Trading Pulse V3.0C - Multi-market contract/setup validation.

This module validates that setup previews are internally consistent with the
selected futures contract. It does not declare a trade profitable and it does
not fabricate execution readiness.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Iterable
import math

from instruments import get_instrument

ENGINE_VERSION = "3.0C"

@dataclass(frozen=True)
class ValidationResult:
    symbol: str
    candidate_id: str
    valid: bool
    checks: dict
    errors: tuple[str, ...]
    preview_risk_points: float | None
    preview_risk_ticks: float | None
    preview_risk_dollars: float | None
    preview_reward_points: float | None
    preview_rr: float | None

    def to_dict(self):
        d = asdict(self)
        d["errors"] = list(self.errors)
        return d

def _aligned(value: float | None, tick: float, tolerance: float = 1e-6) -> bool:
    if value is None or tick <= 0:
        return value is None
    ticks = float(value) / float(tick)
    return abs(ticks - round(ticks)) <= tolerance

def validate_candidate(candidate: Any) -> ValidationResult:
    symbol = str(getattr(candidate, "symbol", "") or "").upper()
    inst = get_instrument(symbol)
    cid = str(getattr(candidate, "candidate_id", "") or "")
    entry = getattr(candidate, "projected_entry", None)
    stop = getattr(candidate, "projected_stop", None)
    target = getattr(candidate, "projected_target", None)
    lower = float(getattr(candidate, "lower_bound"))
    upper = float(getattr(candidate, "upper_bound"))
    zone_type = str(getattr(candidate, "zone_type", "")).lower()

    errors = []
    checks = {}

    checks["symbol_matches_registry"] = bool(symbol == inst.root_symbol)
    checks["valid_zone"] = bool(lower > 0 and upper > lower and zone_type in ("supply", "demand"))
    checks["zone_bounds_tick_aligned"] = _aligned(lower, inst.tick_size) and _aligned(upper, inst.tick_size)
    checks["preview_entry_tick_aligned"] = _aligned(entry, inst.tick_size)
    checks["preview_stop_tick_aligned"] = _aligned(stop, inst.tick_size)
    checks["preview_target_tick_aligned"] = _aligned(target, inst.tick_size)

    risk_points = None
    risk_ticks = None
    risk_dollars = None
    reward_points = None
    rr = None

    if entry is not None and stop is not None:
        risk_points = abs(float(entry) - float(stop))
        risk_ticks = risk_points / inst.tick_size if inst.tick_size > 0 else None
        risk_dollars = inst.dollars_for_points(risk_points)
        checks["positive_preview_risk"] = risk_points > 0
        checks["risk_economics_consistent"] = (
            risk_ticks is not None
            and math.isclose(risk_dollars, risk_ticks * inst.tick_value, rel_tol=1e-9, abs_tol=1e-6)
        )
        if zone_type == "demand":
            checks["stop_on_correct_side"] = float(stop) < lower <= float(entry)
        else:
            checks["stop_on_correct_side"] = float(stop) > upper >= float(entry)
    else:
        checks["positive_preview_risk"] = True
        checks["risk_economics_consistent"] = True
        checks["stop_on_correct_side"] = True

    if entry is not None and target is not None:
        reward_points = abs(float(target) - float(entry))
        if risk_points and risk_points > 0:
            rr = reward_points / risk_points
        if zone_type == "demand":
            checks["target_on_correct_side"] = float(target) > float(entry)
        else:
            checks["target_on_correct_side"] = float(target) < float(entry)
    else:
        checks["target_on_correct_side"] = True

    for name, passed in checks.items():
        if not passed:
            errors.append(name)

    return ValidationResult(
        symbol=symbol,
        candidate_id=cid,
        valid=not errors,
        checks=checks,
        errors=tuple(errors),
        preview_risk_points=round(risk_points, 8) if risk_points is not None else None,
        preview_risk_ticks=round(risk_ticks, 4) if risk_ticks is not None else None,
        preview_risk_dollars=round(risk_dollars, 2) if risk_dollars is not None else None,
        preview_reward_points=round(reward_points, 8) if reward_points is not None else None,
        preview_rr=round(rr, 4) if rr is not None else None,
    )

def validate_candidates(candidates: Iterable[Any]) -> dict:
    results = [validate_candidate(c) for c in candidates]
    return {
        "valid": all(r.valid for r in results),
        "count": len(results),
        "failures": [r.to_dict() for r in results if not r.valid],
        "results": [r.to_dict() for r in results],
    }
