"""
The Trading Pulse - Execution Lifecycle Engine V2.9C

Bridges graded SetupCandidates to deterministic TradeState without allowing
candidate previews to become executable orders.

Hard rules
----------
1. Potential candidate levels are educational/structural previews only.
2. Exact executable entry/stop/targets ONLY come from canonical state.trade.
3. Broker eligibility requires canonical TRADE_READY plus a valid TradeState.
4. This module never places an order and never chooses quantity.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional

ENGINE_VERSION = "2.9C"


@dataclass(frozen=True)
class ExecutionLifecycle:
    candidate_id: Optional[str]
    stage: str
    trade_ready: bool
    broker_eligible: bool
    direction: Optional[str]
    entry: Optional[float]
    stop: Optional[float]
    targets: tuple[float, ...]
    risk_points: Optional[float]
    risk_dollars_per_contract: Optional[float]
    setup_grade: Optional[str]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["targets"] = list(self.targets)
        return d


def _same_candidate_zone(candidate: Any, selected_zone: Any) -> bool:
    if candidate is None or selected_zone is None:
        return False
    try:
        return (
            str(candidate.zone_type).lower() == str(selected_zone.type).lower()
            and str(candidate.timeframe) == str(selected_zone.timeframe)
            and abs(float(candidate.lower_bound) - float(selected_zone.lower_bound)) < 0.001
            and abs(float(candidate.upper_bound) - float(selected_zone.upper_bound)) < 0.001
        )
    except (TypeError, ValueError, AttributeError):
        return False


def candidate_stage(state: Any, candidate: Any) -> str:
    """Current snapshot lifecycle. Does not invent historical transitions."""
    if candidate is None:
        return "NO_CANDIDATE"

    selected = _same_candidate_zone(candidate, getattr(state, "selected_zone", None))
    if not selected:
        lifecycle = str(getattr(candidate, "lifecycle", "FORMING") or "FORMING").upper()
        if lifecycle == "IN_ZONE":
            return "POTENTIAL_IN_ZONE"
        if lifecycle == "APPROACHING":
            return "APPROACHING"
        return "POTENTIAL"

    if (
        str(getattr(state, "setup_state", "")).upper() == "TRADE_READY"
        and getattr(state, "trade", None) is not None
    ):
        return "TRADE_READY"

    confirmation = getattr(state, "confirmation", None)
    if confirmation is None:
        return "ARMED"

    if bool(getattr(confirmation, "structural_trigger", False)):
        return "RISK_VALIDATING"
    if bool(getattr(confirmation, "lower_timeframe_confirmed", False)):
        return "CONFIRMING"
    if bool(getattr(confirmation, "price_in_zone", False)):
        return "ARMED"
    return "WATCHING"


def build_execution_lifecycle(state: Any, candidate: Any = None) -> ExecutionLifecycle:
    """
    Produce a broker-safe snapshot.

    Exact prices are intentionally blank unless canonical MarketState already
    owns a validated TradeState and setup_state == TRADE_READY.
    """
    stage = candidate_stage(state, candidate)
    trade = getattr(state, "trade", None)
    canonical_ready = (
        stage == "TRADE_READY"
        and trade is not None
        and bool(getattr(state, "is_actionable", False))
    )

    candidate_id = getattr(candidate, "candidate_id", None) if candidate is not None else None
    candidate_grade = getattr(candidate, "grade", None) if candidate is not None else None

    if not canonical_ready:
        reason = {
            "POTENTIAL": "Structural candidate only; price/confirmation requirements are not complete.",
            "APPROACHING": "Price is approaching the candidate zone; execution remains locked.",
            "POTENTIAL_IN_ZONE": "Price is in a non-selected candidate zone; canonical execution criteria are not satisfied.",
            "WATCHING": "Canonical execution zone is selected but price has not armed the setup.",
            "ARMED": "Price is in the canonical execution zone; lower-timeframe confirmation is still required.",
            "CONFIRMING": "Lower-timeframe confirmation exists; structural trigger is still required.",
            "RISK_VALIDATING": "Structural trigger exists; deterministic risk validation is in progress.",
        }.get(stage, "No canonical executable trade exists.")
        return ExecutionLifecycle(
            candidate_id=candidate_id,
            stage=stage,
            trade_ready=False,
            broker_eligible=False,
            direction=getattr(state, "setup_direction", None),
            entry=None,
            stop=None,
            targets=(),
            risk_points=None,
            risk_dollars_per_contract=None,
            setup_grade=candidate_grade,
            reason=reason,
        )

    targets = tuple(
        float(t.price)
        for t in (getattr(trade, "targets", None) or [])
        if getattr(t, "price", None) is not None
    )
    return ExecutionLifecycle(
        candidate_id=candidate_id,
        stage="TRADE_READY",
        trade_ready=True,
        broker_eligible=True,
        direction=getattr(trade, "direction", None),
        entry=float(trade.entry),
        stop=float(trade.stop),
        targets=targets,
        risk_points=float(getattr(trade, "risk_points", 0.0)),
        risk_dollars_per_contract=float(getattr(trade, "risk_dollars_per_contract", 0.0)),
        setup_grade=getattr(trade, "setup_grade", None) or candidate_grade,
        reason="Canonical confirmation and structural risk validation are complete. Exact levels come from TradeState.",
    )


def broker_order_intent(state: Any, candidate: Any = None) -> Optional[dict[str, Any]]:
    """
    Future broker adapter contract. Returns None until TRADE_READY.

    Quantity is deliberately None: account-level sizing/risk authorization is
    a separate future gate and must never be guessed by the chart.
    """
    lifecycle = build_execution_lifecycle(state, candidate)
    if not lifecycle.broker_eligible:
        return None

    side = "BUY" if str(lifecycle.direction).upper() == "LONG" else "SELL"
    return {
        "schema_version": ENGINE_VERSION,
        "symbol": getattr(state, "root_symbol", None),
        "candidate_id": lifecycle.candidate_id,
        "setup_grade": lifecycle.setup_grade,
        "side": side,
        "entry": lifecycle.entry,
        "stop": lifecycle.stop,
        "targets": list(lifecycle.targets),
        "risk_points": lifecycle.risk_points,
        "risk_dollars_per_contract": lifecycle.risk_dollars_per_contract,
        "quantity": None,
        "broker_eligible": True,
        "requires_account_risk_authorization": True,
    }


def authorized_broker_order_intent(state: Any, candidate: Any, authorization: Any) -> Optional[dict[str, Any]]:
    """Populate quantity only after a separate deterministic risk authorization."""
    packet = broker_order_intent(state, candidate)
    if packet is None or not getattr(authorization, "approved", False):
        return None
    packet = dict(packet)
    packet["quantity"] = int(getattr(authorization, "contracts", 0))
    packet["requires_account_risk_authorization"] = False
    packet["authorized_risk_dollars"] = float(getattr(authorization, "actual_risk_dollars", 0.0))
    return packet


