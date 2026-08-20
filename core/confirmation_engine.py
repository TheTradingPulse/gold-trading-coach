"""
The Trading Pulse - Confirmation Engine V2.6

Deterministic execution confirmation and risk qualification.
No AI-generated trading values are permitted here.
"""
from __future__ import annotations

from typing import Callable, Optional
import pandas as pd

try:
    from core.market_state import ConfirmationState, TargetState, TradeState, ZoneState
except ImportError:
    from market_state import ConfirmationState, TargetState, TradeState, ZoneState

ENGINE_VERSION = "2.6"
CONFIRMATION_TIMEFRAMES = ["5m", "1m"]
TOUCH_LOOKBACK_BARS = 6
STOP_BUFFER_TICKS = 2
MIN_RR_FOR_READY = 2.0


def _iso(value) -> Optional[str]:
    if value is None:
        return None
    try:
        return pd.Timestamp(value).isoformat()
    except Exception:
        return str(value)


def _ev(event, passed, timeframe, timestamp, price, detail):
    return {
        "event": event,
        "passed": bool(passed),
        "timeframe": timeframe,
        "timestamp": _iso(timestamp),
        "price": round(float(price), 4) if price is not None else None,
        "detail": detail,
    }


def _directional_bar(row, direction):
    if direction == "LONG":
        return float(row["close"]) > float(row["open"])
    if direction == "SHORT":
        return float(row["close"]) < float(row["open"])
    return False


def evaluate_price_action_confirmation(direction, execution_zone, data_loader: Callable):
    c = ConfirmationState(conditions_total=4)

    if direction is None or execution_zone is None:
        c.confirmation_reason = "No directional execution zone."
        c.structural_reason = "Structural evaluation unavailable."
        return c

    for timeframe in CONFIRMATION_TIMEFRAMES:
        df = data_loader(timeframe, limit=12)
        if df is None or len(df) < 4:
            c.evidence.append(_ev(
                "data_available", False, timeframe, None, None,
                f"Insufficient {timeframe} candles for confirmation."
            ))
            continue

        df = df.dropna(subset=["open", "high", "low", "close"])
        if len(df) < 4:
            continue

        recent = df.tail(TOUCH_LOOKBACK_BARS)
        touches = recent[
            (recent["low"] <= execution_zone.upper_bound)
            & (recent["high"] >= execution_zone.lower_bound)
        ]

        if touches.empty:
            c.evidence.append(_ev(
                "zone_interaction", False, timeframe, recent.index[-1],
                float(recent["close"].iloc[-1]),
                f"No recent {timeframe} candle interacted with the execution zone."
            ))
            continue

        touch_time = touches.index[-1]
        touch_bar = touches.iloc[-1]
        c.zone_interaction_time = _iso(touch_time)
        c.evidence.append(_ev(
            "zone_interaction", True, timeframe, touch_time, float(touch_bar["close"]),
            f"Price interacted with the {execution_zone.timeframe} {execution_zone.type} execution zone."
        ))

        last = recent.iloc[-1]
        prev = recent.iloc[-2]
        last_time = recent.index[-1]
        directional = _directional_bar(last, direction)

        c.confirmation_timeframe = timeframe
        c.lower_timeframe_confirmed = directional
        c.evidence.append(_ev(
            "directional_candle", directional, timeframe, last_time, float(last["close"]),
            f"Latest {timeframe} candle " +
            ("closes" if directional else "does not close") +
            f" in the {direction} direction."
        ))

        if direction == "LONG":
            level = float(prev["high"])
            structural = float(last["close"]) > level
            trigger_type = "BREAK_PRIOR_HIGH"
            side = "high"
        else:
            level = float(prev["low"])
            structural = float(last["close"]) < level
            trigger_type = "BREAK_PRIOR_LOW"
            side = "low"

        c.structural_trigger = bool(directional and structural)
        c.trigger_type = trigger_type
        c.trigger_price = round(level, 4)
        c.evidence.append(_ev(
            "structural_break", c.structural_trigger, timeframe, last_time,
            float(last["close"]),
            (
                f"{timeframe} close broke prior {side} {level:.2f} after zone interaction."
                if c.structural_trigger else
                f"Structural trigger pending: {timeframe} close has not broken prior {side} {level:.2f}."
            )
        ))

        c.confirmation_reason = (
            f"{timeframe} directional confirmation detected after execution-zone interaction."
            if directional else
            f"{timeframe} zone interaction detected, but directional confirmation is missing."
        )
        if c.structural_trigger:
            c.trigger_time = _iso(last_time)
            c.structural_reason = (
                f"{timeframe} structural break confirmed at {float(last['close']):.2f}."
            )
        else:
            c.structural_reason = f"{timeframe} structural break is still missing."

        # A valid 5m interaction owns the decision; 1m is fallback only.
        return c

    c.confirmation_reason = "No recent 5m/1m execution-zone interaction."
    c.structural_reason = "Structural trigger waits for execution-zone interaction."
    return c


def build_trade_plan(instrument, current_price, direction, execution_zone, confirmation, opposing_conflict):
    if (
        direction is None
        or execution_zone is None
        or opposing_conflict is not None
        or not confirmation.price_in_zone
        or not confirmation.lower_timeframe_confirmed
        or not confirmation.structural_trigger
    ):
        confirmation.risk_validated = False
        confirmation.risk_reason = "Risk plan waits for a clean, confirmed execution setup."
        return None

    tick = float(instrument.tick_size)
    buffer_points = tick * STOP_BUFFER_TICKS
    entry = float(current_price)

    if direction == "LONG":
        stop = float(execution_zone.lower_bound) - buffer_points
        risk_points = entry - stop
    else:
        stop = float(execution_zone.upper_bound) + buffer_points
        risk_points = stop - entry

    if risk_points <= 0:
        confirmation.risk_validated = False
        confirmation.risk_reason = "Calculated stop does not create positive risk distance."
        confirmation.evidence.append(_ev(
            "risk_validation", False, None, None, entry, confirmation.risk_reason
        ))
        return None

    risk_ticks = risk_points / tick
    risk_dollars = instrument.dollars_for_points(risk_points)
    targets = []

    for multiple, name in [(1.0, "T1"), (2.0, "T2"), (3.0, "T3")]:
        price = entry + risk_points * multiple if direction == "LONG" else entry - risk_points * multiple
        targets.append(TargetState(
            name=name,
            price=round(price, 4),
            reward_points=round(risk_points * multiple, 4),
            reward_ticks=round(risk_ticks * multiple, 2),
            reward_dollars_per_contract=round(risk_dollars * multiple, 2),
            rr_ratio=multiple,
        ))

    confirmation.risk_validated = True
    confirmation.risk_reason = (
        f"Stop is {STOP_BUFFER_TICKS} ticks beyond execution-zone invalidation; "
        f"T2 provides {MIN_RR_FOR_READY:.1f}R."
    )
    confirmation.evidence.append(_ev(
        "risk_validation", True, None, None, entry, confirmation.risk_reason
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
    )


def evaluate_setup_lifecycle(current_price, execution_zone, bias, opposing_conflict, instrument, data_loader):
    c = ConfirmationState(conditions_total=4)

    if execution_zone is None:
        c.missing_conditions = ["Qualifying execution zone required"]
        return "SCANNING", None, c, None

    direction = "LONG" if bias == "bullish" else "SHORT" if bias == "bearish" else None
    c.price_in_zone = execution_zone.contains(current_price)

    if opposing_conflict is not None:
        c.missing_conditions = [
            "Opposing-zone conflict must resolve",
            "Price must be in a clean execution zone",
            "Lower-timeframe confirmation required",
            "Structural trigger required",
            "Risk validation required",
        ]
        c.evidence.append(_ev(
            "opposing_zone_conflict", False, opposing_conflict.timeframe, None,
            current_price,
            f"Price overlaps opposing {opposing_conflict.timeframe} {opposing_conflict.type} zone."
        ))
        return "WATCHING", direction, c, None

    if not c.price_in_zone:
        c.missing_conditions = [
            "Price must reach the execution zone",
            "Lower-timeframe confirmation required",
            "Structural trigger required",
            "Risk validation required",
        ]
        state = "APPROACHING" if float(execution_zone.distance_percent or 0) <= 0.35 else "WATCHING"
        return state, direction, c, None

    c = evaluate_price_action_confirmation(direction, execution_zone, data_loader)
    c.price_in_zone = True

    trade = build_trade_plan(
        instrument, current_price, direction, execution_zone, c, opposing_conflict
    )

    c.conditions_met = sum([
        c.price_in_zone,
        c.lower_timeframe_confirmed,
        c.structural_trigger,
        c.risk_validated,
    ])

    missing = []
    if not c.lower_timeframe_confirmed:
        missing.append("Lower-timeframe confirmation required")
    if not c.structural_trigger:
        missing.append("Structural trigger required")
    if not c.risk_validated:
        missing.append("Risk validation required")
    c.missing_conditions = missing

    if trade is not None and c.conditions_met == c.conditions_total:
        return "TRADE_READY", direction, c, trade
    if c.structural_trigger:
        return "TRIGGER_CONFIRMED", direction, c, None
    if c.lower_timeframe_confirmed:
        return "CONFIRMING", direction, c, None
    return "IN_ZONE", direction, c, None
