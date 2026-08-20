"""
The Trading Pulse - Market State Builder V2.5

Authoritative deterministic market-state builder.

Architecture:
    Market Data
        -> Trend Context
        -> Higher-Timeframe Context Zones
        -> Tactical Execution Zones
        -> Setup Lifecycle
        -> MarketState
        -> Dashboard / Professor / Scanner

Important:
- GC is the first production instrument.
- Existing gold_ohlcv storage remains unchanged for V2.2 safety.
- Higher-timeframe zones provide CONTEXT.
- 1H/15m zones provide actionable EXECUTION areas.
- Wide zones are penalized rather than automatically preferred.
- Opposing-zone overlap creates conflict instead of false certainty.
- Entries, stops, targets, confirmation, and readiness are deterministic when qualified.
- Historical probability remains blank until validated comparable-setup statistics exist.
"""

import sys
import warnings
from pathlib import Path
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORE_DIR = PROJECT_ROOT / "core"
ANALYSIS_DIR = PROJECT_ROOT / "analysis"

# Project currently contains both:
#     C:\TradingPulse\database.py
#     C:\TradingPulse\core\database.py
#
# V2 explicitly prioritizes core\database.py.
for path in (str(PROJECT_ROOT), str(ANALYSIS_DIR), str(CORE_DIR)):
    if path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)


# ---------------------------------------------------------------------
# MODULES
# ---------------------------------------------------------------------

from database import get_connection
from instruments import get_instrument
from market_state import (
    MarketState,
    ZoneState,
    ConfirmationState,
    TargetState,
    TradeState,
    create_empty_market_state,
)
from trend_engine import assess_trend
from zone_engine import detect_supply_zones, detect_demand_zones


TIMEFRAMES = ["M", "W", "D", "4H", "1H", "15m", "5m", "1m"]

CONTEXT_ZONE_TIMEFRAMES = ["D", "4H"]
EXECUTION_ZONE_TIMEFRAMES = ["1H", "15m"]

ALL_ZONE_TIMEFRAMES = (
    CONTEXT_ZONE_TIMEFRAMES
    + EXECUTION_ZONE_TIMEFRAMES
)

TREND_WEIGHTS = {
    "M": 4,
    "W": 4,
    "D": 4,
    "4H": 3,
    "1H": 3,
    "15m": 2,
    "5m": 1,
    "1m": 1,
}

ZONE_TIMEFRAME_WEIGHT = {
    "D": 4,
    "4H": 3,
    "1H": 2,
    "15m": 1,
}


# ---------------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------------

def load_market_data(
    timeframe: str,
    limit: int = 500,
) -> Optional[pd.DataFrame]:

    conn = None

    try:
        conn = get_connection()

        query = """
            SELECT timestamp, open, high, low, close, volume
            FROM gold_ohlcv
            WHERE timeframe = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """

        # pandas 3 warns about raw DBAPI connections.
        # Existing Trading Pulse database access is still valid.
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="pandas only supports SQLAlchemy connectable.*",
            )

            df = pd.read_sql_query(
                query,
                conn,
                params=(timeframe, limit),
            )

        if df.empty:
            return None

        df["timestamp"] = pd.to_datetime(
            df["timestamp"],
            utc=True,
        )

        df = df.sort_values("timestamp")
        df = df.set_index("timestamp")

        return df

    except Exception as exc:
        print(
            f"MarketState data load error "
            f"[{timeframe}]: {exc}"
        )
        return None

    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_latest_market_price():
    for timeframe in [
        "1m",
        "5m",
        "15m",
        "1H",
        "4H",
        "D",
    ]:
        df = load_market_data(
            timeframe,
            limit=1,
        )

        if df is None or df.empty:
            continue

        price = float(df["close"].iloc[-1])

        if pd.isna(price) or price <= 0:
            continue

        return (
            price,
            df.index[-1],
            timeframe,
        )

    return None, None, None


# ---------------------------------------------------------------------
# TRENDS
# ---------------------------------------------------------------------

def build_trends() -> dict[str, str]:
    trends = {}

    for timeframe in TIMEFRAMES:
        df = load_market_data(
            timeframe,
            limit=200,
        )

        if df is None or len(df) < 50:
            trends[timeframe] = "no_data"
            continue

        try:
            trends[timeframe] = assess_trend(df)
        except Exception:
            trends[timeframe] = "no_data"

    return trends


def calculate_weighted_alignment(
    trends: dict[str, str],
):
    bullish_weight = 0
    bearish_weight = 0

    for timeframe, weight in TREND_WEIGHTS.items():
        trend = trends.get(timeframe)

        if trend == "bullish":
            bullish_weight += weight

        elif trend == "bearish":
            bearish_weight += weight

    directional_weight = (
        bullish_weight
        + bearish_weight
    )

    if directional_weight == 0:
        return "neutral", 0.0

    if bullish_weight > bearish_weight:
        return (
            "bullish",
            round(
                bullish_weight
                / directional_weight
                * 100,
                1,
            ),
        )

    if bearish_weight > bullish_weight:
        return (
            "bearish",
            round(
                bearish_weight
                / directional_weight
                * 100,
                1,
            ),
        )

    return "neutral", 50.0


# ---------------------------------------------------------------------
# ZONE HELPERS
# ---------------------------------------------------------------------

def zone_width_points(zone: ZoneState) -> float:
    return (
        zone.upper_bound
        - zone.lower_bound
    )


def zone_width_percent(
    zone: ZoneState,
    current_price: float,
) -> float:

    if current_price <= 0:
        return 0.0

    return (
        zone_width_points(zone)
        / current_price
        * 100
    )


def zone_distance(
    current_price: float,
    lower: float,
    upper: float,
):
    if lower <= current_price <= upper:
        points = 0.0

    elif current_price < lower:
        points = lower - current_price

    else:
        points = current_price - upper

    percent = (
        points / current_price * 100
        if current_price > 0
        else 0.0
    )

    return (
        round(points, 4),
        round(percent, 4),
    )


def convert_zone(
    zone: dict,
    timeframe: str,
    current_price: float,
) -> ZoneState:

    lower = float(zone["lower_bound"])
    upper = float(zone["upper_bound"])

    distance_points, distance_percent = (
        zone_distance(
            current_price,
            lower,
            upper,
        )
    )

    strength = float(
        zone.get("strength", 0) or 0
    )

    if strength >= 85:
        grade = "A"

    elif strength >= 70:
        grade = "B"

    elif strength >= 55:
        grade = "C"

    else:
        grade = "D"

    return ZoneState(
        type=str(
            zone["type"]
        ).lower(),
        lower_bound=lower,
        upper_bound=upper,
        timeframe=timeframe,
        strength=strength,
        freshness_score=float(
            zone.get(
                "freshness_score",
                0,
            ) or 0
        ),
        retest_count=int(
            zone.get(
                "retest_count",
                0,
            ) or 0
        ),
        created_at=zone.get(
            "created_at"
        ),
        grade=grade,
        distance_points=distance_points,
        distance_percent=distance_percent,
        selected=False,
        actionable=False,
    )


def build_zones(
    current_price: float,
):
    supply = []
    demand = []

    for timeframe in ALL_ZONE_TIMEFRAMES:
        df = load_market_data(
            timeframe,
            limit=500,
        )

        if df is None or len(df) < 15:
            continue

        try:
            raw_supply = detect_supply_zones(df)
            raw_demand = detect_demand_zones(df)

            for zone in raw_supply:
                supply.append(
                    convert_zone(
                        zone,
                        timeframe,
                        current_price,
                    )
                )

            for zone in raw_demand:
                demand.append(
                    convert_zone(
                        zone,
                        timeframe,
                        current_price,
                    )
                )

        except Exception as exc:
            print(
                f"MarketState zone error "
                f"[{timeframe}]: {exc}"
            )

    return supply, demand


# ---------------------------------------------------------------------
# ZONE RANKING
# ---------------------------------------------------------------------

def zone_selection_score(
    zone: ZoneState,
    current_price: float,
    execution: bool = False,
) -> float:
    """
    Deterministic ranking score.

    This is NOT probability.

    Rewards:
        strength
        freshness
        timeframe quality
        proximity

    Penalizes:
        retests
        excessive zone width

    Execution zones receive a stronger width penalty because actionable
    trade areas must be precise enough to support later risk validation.
    """

    strength = float(
        zone.strength or 0
    )

    freshness = float(
        zone.freshness_score or 0
    )

    retests = int(
        zone.retest_count or 0
    )

    timeframe_weight = (
        ZONE_TIMEFRAME_WEIGHT.get(
            zone.timeframe,
            0,
        )
    )

    distance_pct = float(
        zone.distance_percent or 0
    )

    width_pct = zone_width_percent(
        zone,
        current_price,
    )

    width_penalty = (
        width_pct * 30
        if execution
        else width_pct * 12
    )

    score = (
        strength
        + freshness * 0.20
        + timeframe_weight * 6
        - retests * 8
        - distance_pct * 10
        - width_penalty
    )

    return round(score, 4)


def directional_candidates(
    current_price: float,
    bias: str,
    supply_zones: list[ZoneState],
    demand_zones: list[ZoneState],
):
    if bias == "bullish":
        return [
            zone
            for zone in demand_zones
            if zone.lower_bound
            <= current_price
        ]

    if bias == "bearish":
        return [
            zone
            for zone in supply_zones
            if zone.upper_bound
            >= current_price
        ]

    return []


def select_context_zone(
    current_price: float,
    bias: str,
    supply_zones: list[ZoneState],
    demand_zones: list[ZoneState],
) -> Optional[ZoneState]:

    candidates = directional_candidates(
        current_price,
        bias,
        supply_zones,
        demand_zones,
    )

    candidates = [
        zone
        for zone in candidates
        if zone.timeframe
        in CONTEXT_ZONE_TIMEFRAMES
    ]

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda zone: zone_selection_score(
            zone,
            current_price,
            execution=False,
        ),
    )


def select_execution_zone(
    current_price: float,
    bias: str,
    supply_zones: list[ZoneState],
    demand_zones: list[ZoneState],
) -> Optional[ZoneState]:

    candidates = directional_candidates(
        current_price,
        bias,
        supply_zones,
        demand_zones,
    )

    candidates = [
        zone
        for zone in candidates
        if zone.timeframe
        in EXECUTION_ZONE_TIMEFRAMES
    ]

    if not candidates:
        return None

    selected = max(
        candidates,
        key=lambda zone: zone_selection_score(
            zone,
            current_price,
            execution=True,
        ),
    )

    selected.selected = True
    selected.actionable = True

    return selected


# ---------------------------------------------------------------------
# CONFLICT DETECTION
# ---------------------------------------------------------------------

def find_opposing_zone_conflict(
    current_price: float,
    bias: str,
    supply_zones: list[ZoneState],
    demand_zones: list[ZoneState],
) -> Optional[ZoneState]:
    """
    Detect whether current price is simultaneously inside a meaningful
    opposing zone.

    This prevents the engine from describing a location as clean demand
    while price is also sitting inside supply.
    """

    if bias == "bullish":
        opposing = supply_zones

    elif bias == "bearish":
        opposing = demand_zones

    else:
        return None

    containing = [
        zone
        for zone in opposing
        if zone.contains(current_price)
    ]

    if not containing:
        return None

    return max(
        containing,
        key=lambda zone: zone_selection_score(
            zone,
            current_price,
            execution=(
                zone.timeframe
                in EXECUTION_ZONE_TIMEFRAMES
            ),
        ),
    )


# ---------------------------------------------------------------------
# STRUCTURAL CONFIRMATION / RISK
# ---------------------------------------------------------------------

CONFIRMATION_TIMEFRAMES = ["5m", "1m"]
MIN_RR_FOR_READY = 2.0
STOP_BUFFER_TICKS = 2


def _directional_bar(row, direction: str) -> bool:
    if direction == "LONG":
        return float(row["close"]) > float(row["open"])
    if direction == "SHORT":
        return float(row["close"]) < float(row["open"])
    return False


def evaluate_lower_timeframe_confirmation(
    direction: Optional[str],
    execution_zone: Optional[ZoneState],
):
    """
    Deterministic confirmation:
    - Price must have traded into the execution zone recently.
    - Latest closed candle must agree with setup direction.
    - Latest close must reclaim/break the prior candle extreme in setup direction.

    5m is preferred; 1m is fallback.
    """
    if direction is None or execution_zone is None:
        return False, False, None, "No directional execution zone."

    for timeframe in CONFIRMATION_TIMEFRAMES:
        df = load_market_data(timeframe, limit=12)
        if df is None or len(df) < 4:
            continue

        df = df.dropna(subset=["open", "high", "low", "close"])
        if len(df) < 4:
            continue

        recent = df.tail(6)
        touched = bool(
            (
                (recent["low"] <= execution_zone.upper_bound)
                & (recent["high"] >= execution_zone.lower_bound)
            ).any()
        )
        if not touched:
            continue

        last = recent.iloc[-1]
        prev = recent.iloc[-2]
        directional = _directional_bar(last, direction)

        if direction == "LONG":
            structural = float(last["close"]) > float(prev["high"])
            reason = "Bullish close broke the prior candle high after zone interaction."
        else:
            structural = float(last["close"]) < float(prev["low"])
            reason = "Bearish close broke the prior candle low after zone interaction."

        if directional and structural:
            return True, True, timeframe, reason

        if directional:
            return True, False, timeframe, (
                f"{timeframe} candle agrees with {direction}, "
                "but structural break is still missing."
            )

        return False, False, timeframe, (
            f"{timeframe} latest candle does not confirm {direction}."
        )

    return False, False, None, "No recent 5m/1m execution-zone interaction."


def build_trade_plan(
    instrument,
    current_price: float,
    direction: Optional[str],
    execution_zone: Optional[ZoneState],
    confirmation: ConfirmationState,
    opposing_conflict: Optional[ZoneState],
):
    """
    Build a deterministic trade plan only after confirmation.

    Entry:
        current confirmed market price
    Stop:
        beyond execution-zone invalidation by two instrument ticks
    Targets:
        1R / 2R / 3R

    This is a rule-based plan, not an AI prediction.
    """
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
        return None

    risk_ticks = risk_points / tick
    risk_dollars = instrument.dollars_for_points(risk_points)

    targets = []
    for multiple, name in [(1.0, "T1"), (2.0, "T2"), (3.0, "T3")]:
        target_price = (
            entry + risk_points * multiple
            if direction == "LONG"
            else entry - risk_points * multiple
        )
        targets.append(
            TargetState(
                name=name,
                price=round(target_price, 4),
                reward_points=round(risk_points * multiple, 4),
                reward_ticks=round(risk_ticks * multiple, 2),
                reward_dollars_per_contract=round(risk_dollars * multiple, 2),
                rr_ratio=multiple,
            )
        )

    confirmation.risk_validated = True
    confirmation.risk_reason = (
        f"Stop is {STOP_BUFFER_TICKS} ticks beyond execution-zone invalidation; "
        f"T2 provides {MIN_RR_FOR_READY:.1f}R."
    )

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


# ---------------------------------------------------------------------
# SETUP LIFECYCLE
# ---------------------------------------------------------------------

def determine_setup_state(
    current_price: float,
    execution_zone: Optional[ZoneState],
    bias: str,
    opposing_conflict: Optional[ZoneState],
    instrument,
):
    confirmation = ConfirmationState(conditions_total=4)

    if execution_zone is None:
        confirmation.missing_conditions = ["Qualifying execution zone required"]
        return "SCANNING", None, confirmation, None

    direction = (
        "LONG" if bias == "bullish"
        else "SHORT" if bias == "bearish"
        else None
    )

    in_zone = execution_zone.contains(current_price)
    confirmation.price_in_zone = in_zone

    if opposing_conflict is not None:
        confirmation.missing_conditions = [
            "Opposing-zone conflict must resolve",
            "Price must be in a clean execution zone",
            "Lower-timeframe confirmation required",
            "Structural trigger required",
            "Risk validation required",
        ]
        return "WATCHING", direction, confirmation, None

    if not in_zone:
        confirmation.missing_conditions = [
            "Price must reach the execution zone",
            "Lower-timeframe confirmation required",
            "Structural trigger required",
            "Risk validation required",
        ]
        state = (
            "APPROACHING"
            if float(execution_zone.distance_percent or 0) <= 0.35
            else "WATCHING"
        )
        return state, direction, confirmation, None

    (
        ltf_confirmed,
        structural_trigger,
        confirmation_tf,
        confirmation_reason,
    ) = evaluate_lower_timeframe_confirmation(direction, execution_zone)

    confirmation.lower_timeframe_confirmed = ltf_confirmed
    confirmation.structural_trigger = structural_trigger
    confirmation.confirmation_timeframe = confirmation_tf
    confirmation.confirmation_reason = confirmation_reason
    confirmation.structural_reason = confirmation_reason

    trade = build_trade_plan(
        instrument,
        current_price,
        direction,
        execution_zone,
        confirmation,
        opposing_conflict,
    )

    confirmation.conditions_met = sum(
        [
            confirmation.price_in_zone,
            confirmation.lower_timeframe_confirmed,
            confirmation.structural_trigger,
            confirmation.risk_validated,
        ]
    )

    missing = []
    if not confirmation.lower_timeframe_confirmed:
        missing.append("Lower-timeframe confirmation required")
    if not confirmation.structural_trigger:
        missing.append("Structural trigger required")
    if not confirmation.risk_validated:
        missing.append("Risk validation required")
    confirmation.missing_conditions = missing

    if trade is not None and confirmation.conditions_met == confirmation.conditions_total:
        return "TRADE_READY", direction, confirmation, trade

    if ltf_confirmed or structural_trigger:
        return "CONFIRMING", direction, confirmation, None

    return "IN_ZONE", direction, confirmation, None


# ---------------------------------------------------------------------
# BUILDER
# ---------------------------------------------------------------------

def build_market_state(
    symbol: str = "GC",
) -> MarketState:

    instrument = get_instrument(
        symbol
    )

    if instrument.root_symbol != "GC":
        raise NotImplementedError(
            "V2.2 storage currently supports GC only. "
            "The MarketState interface is multi-symbol ready."
        )

    state = create_empty_market_state(
        instrument.root_symbol
    )

    (
        price,
        market_timestamp,
        price_timeframe,
    ) = get_latest_market_price()

    if price is None:
        state.warnings.append(
            "No current market price available."
        )
        return state

    state.current_price = round(
        float(price),
        4,
    )

    if market_timestamp is not None:
        state.market_timestamp = (
            pd.Timestamp(
                market_timestamp
            ).isoformat()
        )

    # --------------------------------------------------------------
    # Trend context
    # --------------------------------------------------------------

    trends = build_trends()

    state.trends = trends

    bias, alignment = (
        calculate_weighted_alignment(
            trends
        )
    )

    state.market_bias = bias
    state.alignment_score = alignment

    # --------------------------------------------------------------
    # Zones
    # --------------------------------------------------------------

    (
        supply_zones,
        demand_zones,
    ) = build_zones(
        state.current_price
    )

    state.supply_zones = supply_zones
    state.demand_zones = demand_zones

    context_zone = select_context_zone(
        state.current_price,
        bias,
        supply_zones,
        demand_zones,
    )

    execution_zone = select_execution_zone(
        state.current_price,
        bias,
        supply_zones,
        demand_zones,
    )

    opposing_conflict = (
        find_opposing_zone_conflict(
            state.current_price,
            bias,
            supply_zones,
            demand_zones,
        )
    )

    # selected_zone means actionable execution zone.
    state.selected_zone = execution_zone

    # --------------------------------------------------------------
    # Setup lifecycle
    # --------------------------------------------------------------

    (
        setup_state,
        setup_direction,
        confirmation,
        trade,
    ) = determine_setup_state(
        state.current_price,
        execution_zone,
        bias,
        opposing_conflict,
        instrument,
    )

    state.setup_state = setup_state
    state.setup_direction = setup_direction
    state.confirmation = confirmation

    # Deterministic trade plan exists only when every required condition passes.
    state.trade = trade

    # --------------------------------------------------------------
    # Professor bridge
    # --------------------------------------------------------------

    state.professor_context = {
        "architecture_version": "2.5",
        "price_source_timeframe": price_timeframe,
        "storage_status": "GC-only legacy storage",
        "trade_values_generated_by_ai": False,
        "decision_packet": {
            "setup_state": state.setup_state,
            "direction": state.setup_direction,
            "confirmation": state.confirmation.__dict__,
            "trade": state.trade.__dict__ if state.trade else None,
            "historical_probability": None,
            "guardrail": "Professor explains deterministic state; it does not invent missing trade values.",
        },

        "zone_model": {
            "context_timeframes":
                CONTEXT_ZONE_TIMEFRAMES,
            "execution_timeframes":
                EXECUTION_ZONE_TIMEFRAMES,
            "context_zone":
                context_zone.to_dict()
                if hasattr(
                    context_zone,
                    "to_dict",
                )
                else (
                    context_zone.__dict__
                    if context_zone
                    else None
                ),
            "execution_zone":
                execution_zone.__dict__
                if execution_zone
                else None,
            "opposing_conflict":
                opposing_conflict.__dict__
                if opposing_conflict
                else None,
        },
    }

    state.engine_versions = {
        "market_state": "2.5",
        "trend": "legacy_v1",
        "zones": "legacy_v1",
        "zone_selector": "v2.5_hierarchical",
        "confirmation": "v2.5_price_action",
        "risk": "v2.5_zone_invalidation",
    }

    missing_timeframes = [
        timeframe
        for timeframe, trend
        in trends.items()
        if trend == "no_data"
    ]

    if missing_timeframes:
        state.warnings.append(
            "Missing trend data: "
            + ", ".join(
                missing_timeframes
            )
        )

    if opposing_conflict is not None:
        state.warnings.append(
            "Current price overlaps an opposing "
            f"{opposing_conflict.timeframe} "
            f"{opposing_conflict.type} zone."
        )

    return state


# ---------------------------------------------------------------------
# TERMINAL OUTPUT
# ---------------------------------------------------------------------

def print_market_state(
    state: MarketState,
):

    print()
    print("=" * 68)
    print(
        " THE TRADING PULSE - "
        "LIVE MARKET STATE V2.5"
    )
    print("=" * 68)

    print(
        f"Instrument:        "
        f"{state.root_symbol} - "
        f"{state.instrument_name}"
    )

    print(
        f"Data Symbol:       "
        f"{state.data_symbol}"
    )

    if state.current_price is not None:
        print(
            f"Current Price:     "
            f"${state.current_price:,.2f}"
        )
    else:
        print(
            "Current Price:     NO DATA"
        )

    print(
        f"Market Timestamp:  "
        f"{state.market_timestamp}"
    )

    print(
        f"Market Bias:       "
        f"{state.market_bias.upper()}"
    )

    print(
        f"Alignment:         "
        f"{state.alignment_score:.1f}%"
    )

    print()
    print("TIMEFRAME TRENDS")

    for timeframe in TIMEFRAMES:
        print(
            f"  {timeframe:<4} "
            f"{state.trends.get(timeframe, 'no_data').upper()}"
        )

    print()

    zone_model = (
        state.professor_context
        .get("zone_model", {})
    )

    context_zone = zone_model.get(
        "context_zone"
    )

    execution_zone = zone_model.get(
        "execution_zone"
    )

    conflict = zone_model.get(
        "opposing_conflict"
    )

    print("HIGHER-TIMEFRAME CONTEXT")

    if context_zone:
        print(
            f"  {context_zone['timeframe']} "
            f"{context_zone['type'].upper()} | "
            f"${context_zone['lower_bound']:,.2f} - "
            f"${context_zone['upper_bound']:,.2f}"
        )
    else:
        print("  None")

    print()
    print("EXECUTION ZONE")

    if execution_zone:
        width = (
            execution_zone["upper_bound"]
            - execution_zone["lower_bound"]
        )

        print(
            f"  {execution_zone['timeframe']} "
            f"{execution_zone['type'].upper()}"
        )

        print(
            f"  Range:           "
            f"${execution_zone['lower_bound']:,.2f} - "
            f"${execution_zone['upper_bound']:,.2f}"
        )

        print(
            f"  Width:           "
            f"{width:,.2f} points"
        )

        print(
            f"  Strength:        "
            f"{execution_zone['strength']}"
        )

        print(
            f"  Distance:        "
            f"{execution_zone['distance_points']:,.2f} pts "
            f"({execution_zone['distance_percent']:.3f}%)"
        )
    else:
        print("  None")

    print()
    print("OPPOSING-ZONE CONFLICT")

    if conflict:
        print(
            f"  YES - "
            f"{conflict['timeframe']} "
            f"{conflict['type'].upper()} | "
            f"${conflict['lower_bound']:,.2f} - "
            f"${conflict['upper_bound']:,.2f}"
        )
    else:
        print("  None")

    print()
    print(
        f"Setup State:       "
        f"{state.setup_state}"
    )

    print(
        f"Direction:         "
        f"{state.setup_direction or 'NONE'}"
    )

    print(
        f"Trade Ready:       "
        f"{state.is_actionable}"
    )

    print(
        f"Professor Ready:   "
        f"{state.professor_ready}"
    )

    if state.confirmation.missing_conditions:
        print()
        print("STILL REQUIRED")

        for condition in (
            state.confirmation
            .missing_conditions
        ):
            print(
                f"  - {condition}"
            )

    if state.warnings:
        print()
        print("WARNINGS")

        for warning in state.warnings:
            print(
                f"  - {warning}"
            )

    print("=" * 68)
    print()


if __name__ == "__main__":
    state = build_market_state("GC")
    print_market_state(state)
