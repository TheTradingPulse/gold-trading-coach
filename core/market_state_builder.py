"""
The Trading Pulse - Market State Builder V2.10E

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
- V2.8A adds a canonical LIVE/REPLAY market clock and enforces the replay cutoff at the database boundary.
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
from market_clock import MarketClock, live_clock, replay_clock, normalize_timestamp
from setup_fingerprint import build_setup_fingerprint
from setup_candidate_engine import build_setup_candidates
from data_integrity import evaluate_feed_status
from market_data_provider import fetch_market_data
from market_state import (
    MarketState,
    ZoneState,
    create_empty_market_state,
)
from confirmation_engine import evaluate_setup_lifecycle
from trade_plan_engine import build_structural_trade_plan
from trend_engine import assess_trend
from zone_engine import detect_supply_zones, detect_demand_zones


TIMEFRAMES = ["M", "W", "D", "4H", "1H", "15m", "5m", "1m"]

CONTEXT_ZONE_TIMEFRAMES = ["D", "4H"]
EXECUTION_ZONE_TIMEFRAMES = ["1H", "15m"]
SCALP_ZONE_TIMEFRAMES = ["5m", "1m"]

ALL_ZONE_TIMEFRAMES = (
    CONTEXT_ZONE_TIMEFRAMES
    + EXECUTION_ZONE_TIMEFRAMES
    + SCALP_ZONE_TIMEFRAMES
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
    "5m": 0.75,
    "1m": 0.50,
}


# ---------------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------------

def load_market_data(
    timeframe: str,
    limit: int = 500,
    as_of=None,
    symbol: str = "GC",
) -> Optional[pd.DataFrame]:

    symbol = str(symbol).upper()

    # V3.3G LIVE CANONICAL BOUNDARY:
    # For live/dashboard requests, every futures market -- including GC -- is
    # read directly from the same provider adapter.  Previously GC alone read
    # from gold_ohlcv while Market Watch could read fresh GC=F, allowing a stale
    # database candle to disagree materially with the chart/radar.
    # Historical/replay GC requests retain the database path below; the replay
    # bridge also replaces this loader with point-in-time frames during research.
    if as_of is None:
        return fetch_market_data(symbol, timeframe, limit=limit, as_of=None)

    if symbol != "GC":
        return fetch_market_data(symbol, timeframe, limit=limit, as_of=as_of)

    conn = None

    try:
        conn = get_connection()

        cutoff = normalize_timestamp(as_of) if as_of is not None else None

        if cutoff is None:
            query = """
                SELECT timestamp, open, high, low, close, volume
                FROM gold_ohlcv
                WHERE timeframe = %s
                ORDER BY timestamp DESC
                LIMIT %s
            """
            params = (timeframe, limit)
        else:
            # V2.8A HARD REPLAY GUARDRAIL: future candles cannot cross this boundary.
            query = """
                SELECT timestamp, open, high, low, close, volume
                FROM gold_ohlcv
                WHERE timeframe = %s
                  AND timestamp <= %s
                ORDER BY timestamp DESC
                LIMIT %s
            """
            params = (timeframe, cutoff.to_pydatetime(), limit)

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
                params=params,
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


def get_latest_market_price(as_of=None, symbol="GC"):
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
            as_of=as_of,
            symbol=symbol,
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

def build_trends(as_of=None, symbol="GC") -> dict[str, str]:
    trends = {}

    for timeframe in TIMEFRAMES:
        df = load_market_data(
            timeframe,
            limit=200,
            as_of=as_of,
            symbol=symbol,
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
    as_of=None,
    symbol="GC",
):
    supply = []
    demand = []

    for timeframe in ALL_ZONE_TIMEFRAMES:
        df = load_market_data(
            timeframe,
            limit=500,
            as_of=as_of,
            symbol=symbol,
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
# CONFIRMATION / RISK
# ---------------------------------------------------------------------
# V2.6 delegates evidence, structural confirmation, lifecycle gating,
# and deterministic risk construction to core/confirmation_engine.py.

# ---------------------------------------------------------------------
# BUILDER
# ---------------------------------------------------------------------

def build_market_state(
    symbol: str = "GC",
    as_of=None,
    clock: Optional[MarketClock] = None,
) -> MarketState:

    # V2.8A: one canonical clock controls the entire state build.
    # Passing as_of creates REPLAY mode; omitting it preserves LIVE behavior.
    if clock is None:
        clock = replay_clock(as_of) if as_of is not None else live_clock()
    elif as_of is not None:
        raise ValueError("Pass either clock= or as_of=, not both.")

    cutoff = clock.cutoff

    instrument = get_instrument(
        symbol
    )


    state = create_empty_market_state(
        instrument.root_symbol
    )

    (
        price,
        market_timestamp,
        price_timeframe,
    ) = get_latest_market_price(as_of=cutoff, symbol=instrument.root_symbol)

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

    trends = build_trends(as_of=cutoff, symbol=instrument.root_symbol)

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
        state.current_price,
        as_of=cutoff,
        symbol=instrument.root_symbol,
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

    def clocked_market_data(timeframe: str, limit: int = 500):
        return load_market_data(timeframe, limit=limit, as_of=cutoff, symbol=instrument.root_symbol)

    (
        setup_state,
        setup_direction,
        confirmation,
    ) = evaluate_setup_lifecycle(
        state.current_price,
        execution_zone,
        bias,
        opposing_conflict,
        clocked_market_data,
    )

    # V2.7: confirmation and trade planning are separate deterministic engines.
    trade = build_structural_trade_plan(
        instrument=instrument,
        current_price=state.current_price,
        direction=setup_direction,
        execution_zone=execution_zone,
        confirmation=confirmation,
        opposing_conflict=opposing_conflict,
        supply_zones=supply_zones,
        demand_zones=demand_zones,
    )

    confirmation.conditions_met = sum([
        confirmation.price_in_zone,
        confirmation.lower_timeframe_confirmed,
        confirmation.structural_trigger,
        confirmation.risk_validated,
    ])

    missing = []
    if opposing_conflict is not None:
        missing.append("Opposing-zone conflict must resolve")
    if not confirmation.price_in_zone:
        missing.append("Price must be in a clean execution zone")
    if not confirmation.lower_timeframe_confirmed:
        missing.append("Lower-timeframe confirmation required")
    if not confirmation.structural_trigger:
        missing.append("Structural trigger required")
    if not confirmation.risk_validated:
        missing.append("Risk validation required")
    confirmation.missing_conditions = missing

    if trade is not None and confirmation.conditions_met == confirmation.conditions_total:
        setup_state = "TRADE_READY"
    elif confirmation.structural_trigger:
        setup_state = "RISK_VALIDATING"

    state.setup_state = setup_state
    state.setup_direction = setup_direction
    state.confirmation = confirmation
    state.trade = trade

    # V2.10E DATA-INTEGRITY BROKER GATE.
    # Yahoo GC=F remains useful for education/research/planned levels, but delayed
    # continuous/front-month data can never become executable/broker eligible.
    feed_status = evaluate_feed_status(state.market_timestamp, requested_symbol=instrument.data_symbol)
    if not feed_status.execution_eligible:
        if state.trade is not None or state.setup_state in ("TRADE_READY", "RISK_VALIDATING"):
            state.warnings.append("Execution blocked by data-integrity gate: " + feed_status.reason)
        state.trade = None
        state.confirmation.risk_validated = False
        state.confirmation.conditions_met = sum([
            state.confirmation.price_in_zone,
            state.confirmation.lower_timeframe_confirmed,
            state.confirmation.structural_trigger,
            state.confirmation.risk_validated,
        ])
        if "Execution-grade real-time feed required" not in state.confirmation.missing_conditions:
            state.confirmation.missing_conditions.append("Execution-grade real-time feed required")
        if state.setup_state in ("TRADE_READY", "RISK_VALIDATING"):
            state.setup_state = "WATCHING"

    # V2.9B: one setup grade everywhere.  If a deterministic trade plan exists,
    # its displayed grade is the exact SetupCandidate grade for the selected zone,
    # not the older raw zone grade.
    if state.trade is not None and state.selected_zone is not None:
        for _candidate in build_setup_candidates(state):
            if _candidate.is_selected_zone:
                state.trade.setup_grade = _candidate.grade
                break

    # --------------------------------------------------------------
    # Professor bridge
    # --------------------------------------------------------------

    state.professor_context = {
        "architecture_version": "2.12",
        "data_provenance": feed_status.to_dict(),
        "setup_fingerprint": build_setup_fingerprint(state, clock=clock),
        "market_clock": clock.to_dict(),
        "replay_guardrail": {
            "enabled": clock.is_replay,
            "cutoff": clock.cutoff_iso,
            "future_data_allowed": False if clock.is_replay else None,
        },
        "price_source_timeframe": price_timeframe,
        "storage_status": "GC database / multi-market Yahoo reference adapter",
        "trade_values_generated_by_ai": False,
        "decision_packet": {
            "setup_state": state.setup_state,
            "direction": state.setup_direction,
            "confirmation": state.confirmation.__dict__,
            "confirmation_evidence": state.confirmation.evidence,
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
        "market_state": "2.10E",
        "data_integrity": "v2.10E",
        "setup_fingerprint": "v2.8B",
        "historical_replay": "v2.8C",
        "market_clock": "v2.8A",
        "trend": "legacy_v1",
        "zones": "legacy_v1",
        "zone_selector": "v2.5_hierarchical",
        "confirmation": "v2.7_evidence_engine",
        "trade_plan": "v2.7_structural_targets",
        "setup_candidate": "v2.12_calibrated_quality_gates",
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
        "MARKET STATE V2.8C"
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

############################################################




