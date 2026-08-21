"""
The Trading Pulse - Structural Trade Plan Engine V2.7

Builds deterministic entries, structural invalidation stops, structural targets,
contract risk, and reward-to-risk qualification.

Targets come from detected opposing market structure. This engine does NOT
manufacture arbitrary 1R/2R/3R targets and does NOT generate probability.
"""
from __future__ import annotations

from typing import Optional

try:
    from core.risk_model import structural_stop
except ImportError:
    from risk_model import structural_stop

try:
    from core.market_state import ConfirmationState, TargetState, TradeState, ZoneState
except ImportError:
    from market_state import ConfirmationState, TargetState, TradeState, ZoneState

ENGINE_VERSION = "3.1E"
STOP_BUFFER_TICKS = None  # replaced by canonical adaptive structural risk model
MIN_RR_FOR_READY = 2.0
MAX_TARGETS = 3


def _ev(event, passed, price, detail):
    return {
        "event": event,
        "passed": bool(passed),
        "timeframe": None,
        "timestamp": None,
        "price": round(float(price), 4) if price is not None else None,
        "detail": detail,
    }


def _zone_dict(zone: Optional[ZoneState]):
    if zone is None:
        return None
    return {
        "type": zone.type,
        "timeframe": zone.timeframe,
        "lower_bound": zone.lower_bound,
        "upper_bound": zone.upper_bound,
        "strength": zone.strength,
        "grade": zone.grade,
        "created_at": zone.created_at,
    }


def _structural_target_candidates(
    direction: str,
    entry: float,
    supply_zones: list[ZoneState],
    demand_zones: list[ZoneState],
) -> list[tuple[float, ZoneState]]:
    """
    LONG  -> target the near edge of supply above entry.
    SHORT -> target the near edge of demand below entry.

    Using the near edge is intentionally conservative: reward is measured only
    to the first contact with opposing structure.
    """
    candidates: list[tuple[float, ZoneState]] = []

    if direction == "LONG":
        for zone in supply_zones:
            target_price = float(zone.lower_bound)
            if target_price > entry:
                candidates.append((target_price, zone))
        candidates.sort(key=lambda item: item[0])

    elif direction == "SHORT":
        for zone in demand_zones:
            target_price = float(zone.upper_bound)
            if target_price < entry:
                candidates.append((target_price, zone))
        candidates.sort(key=lambda item: item[0], reverse=True)

    # Deduplicate heavily overlapping target prices while preserving the nearest
    # structural obstacle first.
    deduped: list[tuple[float, ZoneState]] = []
    for price, zone in candidates:
        if not deduped:
            deduped.append((price, zone))
            continue

        prior_price = deduped[-1][0]
        if abs(price - prior_price) <= max(abs(entry) * 0.0005, 0.5):
            # Keep the stronger zone when two target edges are effectively equal.
            prior_zone = deduped[-1][1]
            if float(zone.strength or 0) > float(prior_zone.strength or 0):
                deduped[-1] = (price, zone)
        else:
            deduped.append((price, zone))

    return deduped


def build_structural_trade_plan(
    instrument,
    current_price: float,
    direction: Optional[str],
    execution_zone: Optional[ZoneState],
    confirmation: ConfirmationState,
    opposing_conflict: Optional[ZoneState],
    supply_zones: list[ZoneState],
    demand_zones: list[ZoneState],
) -> Optional[TradeState]:
    """
    Return TradeState only when the confirmed setup also has acceptable
    structural reward-to-risk.

    A structural trigger can therefore exist without TRADE_READY status.
    """
    confirmation.risk_validated = False

    if direction is None or execution_zone is None:
        confirmation.risk_reason = "Trade plan requires a directional execution zone."
        return None

    if opposing_conflict is not None:
        confirmation.risk_reason = "Trade plan rejected while price overlaps opposing structure."
        confirmation.evidence.append(_ev(
            "risk_validation", False, current_price, confirmation.risk_reason
        ))
        return None

    if not (
        confirmation.price_in_zone
        and confirmation.lower_timeframe_confirmed
        and confirmation.structural_trigger
    ):
        confirmation.risk_reason = "Trade plan waits for complete price-action confirmation."
        return None

    tick = float(instrument.tick_size)
    if tick <= 0:
        confirmation.risk_reason = "Instrument tick size is invalid."
        return None

    entry = float(current_price)
    risk_model = structural_stop(
        instrument, direction, entry,
        float(execution_zone.lower_bound), float(execution_zone.upper_bound),
        str(execution_zone.timeframe or "15m"),
    )
    stop = risk_model.stop
    buffer_points = risk_model.buffer_points
    risk_points = risk_model.risk_points

    if risk_points <= 0:
        confirmation.risk_reason = "Structural stop does not create positive risk distance."
        confirmation.evidence.append(_ev(
            "risk_validation", False, entry, confirmation.risk_reason
        ))
        return None

    risk_ticks = risk_model.risk_ticks
    risk_dollars = risk_model.risk_dollars_per_contract

    structural = _structural_target_candidates(
        direction, entry, supply_zones, demand_zones
    )

    if not structural:
        confirmation.risk_reason = "No opposing structural target exists beyond entry."
        confirmation.evidence.append(_ev(
            "risk_validation", False, entry, confirmation.risk_reason
        ))
        return None

    targets: list[TargetState] = []
    for index, (target_price, zone) in enumerate(structural[:MAX_TARGETS], start=1):
        reward_points = (
            target_price - entry
            if direction == "LONG"
            else entry - target_price
        )
        if reward_points <= 0:
            continue

        reward_ticks = reward_points / tick
        reward_dollars = instrument.dollars_for_points(reward_points)
        rr = reward_points / risk_points

        targets.append(TargetState(
            name=f"T{index} {zone.timeframe or ''} {zone.type.upper()}".strip(),
            price=round(target_price, 4),
            reward_points=round(reward_points, 4),
            reward_ticks=round(reward_ticks, 2),
            reward_dollars_per_contract=round(reward_dollars, 2),
            rr_ratio=round(rr, 2),
        ))

    if not targets:
        confirmation.risk_reason = "Opposing zones were found, but none produced positive reward."
        return None

    nearest_target = targets[0]
    nearest_zone = structural[0][1]
    nearest_rr = float(nearest_target.rr_ratio or 0)

    # The nearest opposing structure is the gating target. We do not approve a
    # trade merely because a farther target has 2R if price must first run into
    # closer opposing structure.
    if nearest_rr < MIN_RR_FOR_READY:
        confirmation.risk_reason = (
            f"Trade rejected: nearest opposing {nearest_zone.timeframe} "
            f"{nearest_zone.type} offers only {nearest_rr:.2f}R; "
            f"{MIN_RR_FOR_READY:.2f}R required."
        )
        confirmation.evidence.append(_ev(
            "risk_validation", False, entry, confirmation.risk_reason
        ))
        return None

    confirmation.risk_validated = True
    confirmation.risk_reason = (
        f"Structural risk accepted: {risk_model.buffer_ticks:.0f}-tick adaptive buffer "
        f"({risk_model.buffer_points:.4f} pts) beyond execution-zone invalidation and "
        f"{nearest_rr:.2f}R available before "
        f"nearest opposing {nearest_zone.timeframe} {nearest_zone.type}."
    )
    confirmation.evidence.append(_ev(
        "risk_validation", True, entry, confirmation.risk_reason
    ))

    return TradeState(
        direction=direction,
        entry=round(entry, 4),
        stop=round(stop, 4),
        targets=targets,
        risk_points=round(risk_points, 4),
        risk_ticks=round(risk_ticks, 2),
        risk_dollars_per_contract=round(risk_dollars, 2),
        setup_grade=execution_zone.grade,
        historical_probability=None,
        probability_sample_size=None,
        invalidation_reason=(
            f"{direction} thesis invalidates beyond the "
            f"{execution_zone.timeframe} {execution_zone.type} execution zone."
        ),
        target_model="opposing_structure_near_edge",
        nearest_opposing_zone=_zone_dict(nearest_zone),
        room_to_target_points=nearest_target.reward_points,
        minimum_required_rr=MIN_RR_FOR_READY,
    )
