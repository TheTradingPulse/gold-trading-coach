"""Canonical, versioned contracts shared by live and research adapters.

These types contain no detection, scoring, data fetching, or promotion logic.
They make incompatible generations explicit rather than silently coercing them.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Mapping

CONTRACT_VERSION = "TP_CANONICAL_CONTRACTS_1"
ALLOWED_DIRECTIONS = {"LONG", "SHORT"}
ALLOWED_PATTERNS = {"RBR", "DBR", "RBD", "DBD", "DEMAND", "SUPPLY", "UNKNOWN"}


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
