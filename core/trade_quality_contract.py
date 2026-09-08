"""Canonical, outcome-blind trade-quality contract.

This module answers one question only: did a proposed trade become valid using
information available at the decision timestamp?  It deliberately does not
inspect future bars or decide whether a trade won.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Mapping, Optional


CONTRACT_VERSION = "TP_TRADE_QUALITY_1"
ALLOWED_TARGET_R = (3, 5)
MAX_RISK_DOLLARS = 300.0


class SetupFamily(str, Enum):
    TREND_CONTINUATION = "TREND_CONTINUATION"
    BREAKOUT_RETEST = "BREAKOUT_RETEST"
    LIQUIDITY_SWEEP_REVERSAL = "LIQUIDITY_SWEEP_REVERSAL"


@dataclass(frozen=True)
class TradeProposal:
    setup_family: str
    direction: str
    decision_ts: str
    entry: float
    stop: float
    target_r: int
    risk_dollars: float
    room_r: float
    trend_4h: str
    location_valid: bool
    displacement: bool
    confirmation_close: bool
    structure_break_15m: bool = False
    pullback_valid: bool = False
    breakout_confirmed: bool = False
    retest_confirmed: bool = False
    liquidity_sweep: bool = False
    reclaim_confirmed: bool = False
    opposing_structure_clear: bool = True


@dataclass(frozen=True)
class QualityDecision:
    contract_version: str
    status: str
    grade: str
    score: int
    setup_family: str
    direction: str
    decision_ts: str
    entry: float
    stop: float
    t1: float
    t2: float
    target_r: int
    reasons: tuple[str, ...]
    rejection_reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        result = asdict(self)
        result["reasons"] = list(self.reasons)
        result["rejection_reasons"] = list(self.rejection_reasons)
        return result


def _aligned(direction: str, trend: str) -> bool:
    return (direction == "LONG" and trend == "BULLISH") or (
        direction == "SHORT" and trend == "BEARISH"
    )


def _levels(direction: str, entry: float, stop: float, target_r: int) -> tuple[float, float]:
    risk = abs(entry - stop)
    sign = 1.0 if direction == "LONG" else -1.0
    return entry + sign * risk * 3.0, entry + sign * risk * float(target_r)


def evaluate_trade_quality(proposal: TradeProposal | Mapping) -> QualityDecision:
    """Apply hard visual/setup gates without looking at the outcome."""
    p = proposal if isinstance(proposal, TradeProposal) else TradeProposal(**proposal)
    family = str(p.setup_family).upper()
    direction = str(p.direction).upper()
    trend = str(p.trend_4h).upper()
    rejected: list[str] = []
    reasons: list[str] = []

    if family not in {item.value for item in SetupFamily}:
        rejected.append("UNKNOWN_SETUP_FAMILY")
    if direction not in {"LONG", "SHORT"}:
        rejected.append("INVALID_DIRECTION")
    if p.target_r not in ALLOWED_TARGET_R:
        rejected.append("TARGET_MUST_BE_3R_OR_5R")
    if p.entry <= 0 or p.stop <= 0 or p.entry == p.stop:
        rejected.append("INVALID_STRUCTURAL_RISK")
    elif (direction == "LONG" and p.stop >= p.entry) or (direction == "SHORT" and p.stop <= p.entry):
        rejected.append("STOP_NOT_BEYOND_INVALIDATION")
    if p.risk_dollars <= 0 or p.risk_dollars > MAX_RISK_DOLLARS:
        rejected.append("RISK_EXCEEDS_300_DOLLAR_MAX")
    if p.room_r < p.target_r or not p.opposing_structure_clear:
        rejected.append("INSUFFICIENT_CLEAR_PROFIT_ROOM")
    if not p.location_valid:
        rejected.append("NO_MEANINGFUL_LOCATION")
    if not p.displacement:
        rejected.append("NO_DISPLACEMENT")
    if not p.confirmation_close:
        rejected.append("NO_CONFIRMATION_CLOSE")

    aligned = _aligned(direction, trend)
    if family == SetupFamily.TREND_CONTINUATION.value:
        if not aligned:
            rejected.append("COUNTERTREND_CONTINUATION")
        if not p.pullback_valid:
            rejected.append("NO_VALID_PULLBACK")
        if not p.structure_break_15m:
            rejected.append("NO_15M_CONTINUATION_BREAK")
    elif family == SetupFamily.BREAKOUT_RETEST.value:
        if trend not in {"NEUTRAL", "NO_DATA"} and not aligned:
            rejected.append("BREAKOUT_OPPOSES_4H_STRUCTURE")
        if not p.breakout_confirmed:
            rejected.append("NO_CONFIRMED_BREAKOUT")
        if not p.retest_confirmed:
            rejected.append("NO_CONFIRMED_RETEST")
        if not p.structure_break_15m:
            rejected.append("NO_15M_REENTRY_BREAK")
    elif family == SetupFamily.LIQUIDITY_SWEEP_REVERSAL.value:
        if not p.liquidity_sweep:
            rejected.append("NO_LIQUIDITY_SWEEP")
        if not p.reclaim_confirmed:
            rejected.append("NO_RECLAIM")
        if not p.structure_break_15m:
            rejected.append("NO_15M_CHANGE_OF_CHARACTER")

    score = 0
    score += 15 if p.location_valid else 0
    score += 15 if p.displacement else 0
    score += 15 if p.confirmation_close else 0
    score += 15 if p.structure_break_15m else 0
    score += 10 if aligned else (10 if family == SetupFamily.LIQUIDITY_SWEEP_REVERSAL.value and p.reclaim_confirmed else 0)
    score += 10 if p.opposing_structure_clear and p.room_r >= p.target_r else 0
    score += 10 if family == SetupFamily.TREND_CONTINUATION.value and p.pullback_valid else 0
    score += 10 if family == SetupFamily.BREAKOUT_RETEST.value and p.breakout_confirmed and p.retest_confirmed else 0
    score += 10 if family == SetupFamily.LIQUIDITY_SWEEP_REVERSAL.value and p.liquidity_sweep and p.reclaim_confirmed else 0
    score = min(score, 100)

    if not rejected:
        reasons.extend((
            "Setup was valid at the decision timestamp.",
            f"Clear structural room supports the {p.target_r}R objective.",
            "Entry follows confirmation; zone contact alone is never an entry.",
        ))
    grade = "A+" if score >= 90 else "A" if score >= 80 else "B" if score >= 70 else "C" if score >= 60 else "D"
    status = "READY" if not rejected else "REJECTED"
    t1, t2 = _levels(direction, float(p.entry), float(p.stop), p.target_r) if direction in {"LONG", "SHORT"} and p.entry != p.stop else (0.0, 0.0)
    return QualityDecision(
        CONTRACT_VERSION, status, grade, score, family, direction, p.decision_ts,
        float(p.entry), float(p.stop), round(t1, 8), round(t2, 8), p.target_r,
        tuple(reasons), tuple(dict.fromkeys(rejected)),
    )


def decision_time_chart_levels(decision: QualityDecision) -> Optional[dict]:
    """Return only the four permitted overlays, starting at decision time."""
    if decision.status != "READY":
        return None
    return {
        "start_ts": decision.decision_ts,
        "Entry": decision.entry,
        "Stop": decision.stop,
        "T1": decision.t1,
        "T2": decision.t2,
    }
