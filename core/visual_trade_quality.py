"""Fail-closed visual trade-quality gate.

This module does not discover trades and never inspects future outcome data.
It validates whether a proposed chart setup was visually coherent at entry.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VisualTrade:
    direction: str
    structure_4h: str
    structure_1h: str
    confirmation_15m: bool
    countertrend_reversal_confirmed: bool
    entry: float
    stop: float
    opposing_level: float
    mgc_contracts: int = 1
    mgc_dollars_per_point: float = 10.0
    max_risk_dollars: float = 300.0


@dataclass(frozen=True)
class VisualDecision:
    accepted: bool
    setup_type: str
    risk_points: float
    risk_dollars: float
    room_r: float
    reasons: tuple[str, ...]


def evaluate_visual_trade(t: VisualTrade, minimum_room_r: float = 2.0) -> VisualDecision:
    direction = t.direction.upper()
    h4 = t.structure_4h.upper()
    h1 = t.structure_1h.upper()
    if direction not in {"LONG", "SHORT"}:
        raise ValueError("direction must be LONG or SHORT")

    risk_points = (t.entry - t.stop) if direction == "LONG" else (t.stop - t.entry)
    risk_dollars = risk_points * t.mgc_dollars_per_point * t.mgc_contracts
    room_points = (t.opposing_level - t.entry) if direction == "LONG" else (t.entry - t.opposing_level)
    room_r = room_points / risk_points if risk_points > 0 else 0.0

    aligned = (direction == "LONG" and h4 == h1 == "BULLISH") or (
        direction == "SHORT" and h4 == h1 == "BEARISH"
    )
    setup_type = "TREND_CONTINUATION" if aligned else "COUNTERTREND_REVERSAL"
    reasons: list[str] = []

    if risk_points <= 0:
        reasons.append("INVALID_STRUCTURAL_STOP")
    if not t.confirmation_15m:
        reasons.append("NO_15M_CONFIRMATION")
    if not aligned and not t.countertrend_reversal_confirmed:
        reasons.append("COUNTERTREND_WITHOUT_REVERSAL_CONFIRMATION")
    if risk_dollars > t.max_risk_dollars:
        reasons.append("RISK_EXCEEDS_MAXIMUM")
    if room_r < minimum_room_r:
        reasons.append("INSUFFICIENT_PROFIT_ROOM")

    return VisualDecision(
        accepted=not reasons,
        setup_type=setup_type,
        risk_points=risk_points,
        risk_dollars=risk_dollars,
        room_r=room_r,
        reasons=tuple(reasons),
    )
