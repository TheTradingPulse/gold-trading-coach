"""Canonical, versioned contracts shared by live and research adapters.

These types contain no detection, scoring, data fetching, or promotion logic.
They make incompatible generations explicit rather than silently coercing them.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Mapping

CONTRACT_VERSION = "TP_CANONICAL_CONTRACTS_1"
TRADE_RECORD_VERSION = "TP_CANONICAL_TRADE_RECORD_1"
ALLOWED_DIRECTIONS = {"LONG", "SHORT"}
ALLOWED_PATTERNS = {"RBR", "DBR", "RBD", "DBD", "DEMAND", "SUPPLY", "UNKNOWN"}
ALLOWED_SETUP_FAMILIES = {"TREND_PULLBACK", "BREAKOUT_RETEST", "LIQUIDITY_SWEEP_RECLAIM", "CONFIRMED_REVERSAL"}
ALLOWED_DATA_SPLITS = {"DEVELOPMENT", "CALIBRATION", "HOLDOUT", "LIVE_SHADOW"}


def _float(value: Any) -> float | None:
    try: return float(value) if value is not None else None
    except (TypeError, ValueError): return None


@dataclass(frozen=True)
class CanonicalSetup:
    setup_id: str
    source_generation: str
    detector_version: str
    symbol: str
    direction: str
    pattern: str
    timeframe: str
    formed_at: str | None
    entry_ts: str | None
    entry: float | None
    stop: float | None
    risk: float | None
    structure_score10: float | None
    evidence_score10: float | None = None
    execution_status: str = "UNVERIFIED"
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> list[str]:
        errors=[]
        if not self.setup_id: errors.append("setup_id_missing")
        if self.direction not in ALLOWED_DIRECTIONS: errors.append("direction_invalid")
        if self.pattern not in ALLOWED_PATTERNS: errors.append("pattern_invalid")
        if self.entry is not None and self.stop is not None:
            actual=abs(self.entry-self.stop)
            if actual <= 0: errors.append("risk_nonpositive")
            if self.risk is not None and abs(actual-self.risk)>max(1e-8,actual*1e-6): errors.append("risk_mismatch")
            if self.direction=="LONG" and self.stop>=self.entry: errors.append("long_stop_not_below_entry")
            if self.direction=="SHORT" and self.stop<=self.entry: errors.append("short_stop_not_above_entry")
        if self.structure_score10 is not None and not 0<=self.structure_score10<=10: errors.append("structure_score_out_of_range")
        if self.evidence_score10 is not None and not 0<=self.evidence_score10<=10: errors.append("evidence_score_out_of_range")
        if self.formed_at and self.entry_ts:
            try:
                if datetime.fromisoformat(self.entry_ts.replace("Z","+00:00")) < datetime.fromisoformat(self.formed_at.replace("Z","+00:00")):
                    errors.append("entry_before_formation")
            except Exception: errors.append("timestamp_invalid")
        return errors

    def to_dict(self) -> dict[str, Any]: return asdict(self)


@dataclass(frozen=True)
class CanonicalOutcome:
    setup_id: str
    outcome_version: str
    max_verified_r: float | None
    max_possible_r: float | None
    same_bar_ambiguous: bool = False
    cost_r: float = 0.0

    def validate(self) -> list[str]:
        errors=[]; v=_float(self.max_verified_r); p=_float(self.max_possible_r)
        if v is not None and p is not None and v>p+1e-9: errors.append("verified_exceeds_possible")
        if self.cost_r<0: errors.append("negative_cost")
        return errors

    def verified_hit(self, rr: int) -> bool:
        value=_float(self.max_verified_r)
        return value is not None and value>=int(rr)


@dataclass(frozen=True)
class EvidenceDecision:
    setup_id: str
    policy_version: str
    tier: str
    structure_score10: float | None
    evidence_score10: float | None
    sample: int
    target_rr: int | None
    execution_verified: bool
    reason: str

    def live_eligible(self) -> bool:
        return self.tier in {"WATCH", "ELITE"} and self.execution_verified and self.evidence_score10 is not None



@dataclass(frozen=True)
class CanonicalTradeRecord:
    """One immutable trade definition shared by research, charts and live code."""

    trade_id: str
    detector_version: str
    symbol: str
    contract: str
    setup_family: str
    direction: str
    context_timeframe: str
    execution_timeframe: str
    detected_at: str
    confirmed_at: str
    entry: float
    stop: float
    target_1r: float
    target_2r: float
    target_3r: float
    risk_points: float
    risk_ticks: float
    risk_dollars: float
    quantity: int
    structure_4h: str
    structure_1h: str
    confirmation_15m: bool
    opposing_level: float
    available_room_r: float
    data_split: str
    data_source: str
    record_version: str = TRADE_RECORD_VERSION
    zone_id: str | None = None
    zone_created_at: str | None = None
    zone_touch_count: int | None = None
    outcome_status: str = "UNRESOLVED"
    outcome_version: str | None = None
    max_verified_r: float | None = None
    same_bar_ambiguous: bool = False
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def validate(self, *, max_risk_dollars: float = 300.0) -> list[str]:
        errors: list[str] = []
        direction = self.direction.upper()
        if not self.trade_id: errors.append("trade_id_missing")
        if direction not in ALLOWED_DIRECTIONS: errors.append("direction_invalid")
        if self.setup_family not in ALLOWED_SETUP_FAMILIES: errors.append("setup_family_invalid")
        if self.data_split not in ALLOWED_DATA_SPLITS: errors.append("data_split_invalid")
        if not self.contract: errors.append("contract_missing")
        if self.quantity <= 0: errors.append("quantity_nonpositive")
        if self.risk_points <= 0: errors.append("risk_points_nonpositive")
        if self.risk_ticks <= 0: errors.append("risk_ticks_nonpositive")
        if self.risk_dollars <= 0: errors.append("risk_dollars_nonpositive")
        if self.risk_dollars > max_risk_dollars: errors.append("risk_exceeds_maximum")
        actual_risk = abs(self.entry - self.stop)
        if abs(actual_risk - self.risk_points) > max(1e-8, actual_risk * 1e-6):
            errors.append("risk_points_mismatch")
        sign = 1.0 if direction == "LONG" else -1.0
        if direction == "LONG" and self.stop >= self.entry: errors.append("long_stop_not_below_entry")
        if direction == "SHORT" and self.stop <= self.entry: errors.append("short_stop_not_above_entry")
        for rr, target in ((1, self.target_1r), (2, self.target_2r), (3, self.target_3r)):
            expected = self.entry + sign * rr * self.risk_points
            if abs(target - expected) > max(1e-8, abs(expected) * 1e-6):
                errors.append(f"target_{rr}r_mismatch")
        if self.available_room_r < 2.0: errors.append("insufficient_profit_room")
        if not self.confirmation_15m: errors.append("confirmation_missing")
        try:
            detected = datetime.fromisoformat(self.detected_at.replace("Z", "+00:00"))
            confirmed = datetime.fromisoformat(self.confirmed_at.replace("Z", "+00:00"))
            if confirmed < detected: errors.append("confirmation_before_detection")
        except Exception:
            errors.append("timestamp_invalid")
        if self.outcome_status != "UNRESOLVED" and not self.outcome_version:
            errors.append("resolved_outcome_version_missing")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
