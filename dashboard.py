"""
The Trading Pulse
Gold Trading Coach V2.1

Dashboard-first development build.

V2.1 goals:
- Make the live chart the center of the application
- Support multiple chart timeframes
- Surface market bias and setup status immediately
- Show the best supply/demand zones to watch
- Preserve the existing journal, statistics and backtest functionality
- Do NOT fabricate probability or Professor outputs before those engines exist

This file intentionally continues using the existing V1 engines so that
the dashboard can be upgraded incrementally without replacing the entire
application at once.
"""

import os
import sys
from datetime import datetime, timezone
from io import StringIO

import numpy as np
import pandas as pd
import streamlit as st
import altair as alt

# ---------------------------------------------------------------------
# PATHS / EXISTING ENGINES
# ---------------------------------------------------------------------

sys.path.insert(0, "core")
sys.path.insert(0, "analysis")

from streamlit_autorefresh import st_autorefresh

from database import get_connection
from zone_engine import (
    load_data,
    detect_supply_zones,
    detect_demand_zones,
    is_price_near_zone,
)
from trade_engine import (
    get_current_price,
    get_trends,
    calculate_alignment,
    grade_setup,
)
from live_data_engine import (
    fetch_latest_data,
    get_data_source_name,
)
from journal_engine import (
    calculate_statistics,
    get_all_trades,
    update_outcome,
)
from dna_engine import (
    log_trade_with_dna,
    analyze_dna_performance,
)
from ai_explainer import generate_explanation
from news_engine import (
    generate_news_warning,
    get_confidence_adjustment,
    display_news_calendar,
)
from backtest_engine import (
    run_backtest,
    get_available_years,
)


# ---------------------------------------------------------------------
# STREAMLIT CONFIG
# ---------------------------------------------------------------------

st.set_page_config(
    page_title="The Trading Pulse | Gold",
    page_icon="🥇",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Refresh once per minute.
st_autorefresh(interval=60 * 1000, key="v2_auto_refresh")


# ---------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------

APP_NAME = "The Trading Pulse"
COACH_NAME = "Gold Trading Coach"

DISPLAY_SYMBOL = "GC"
DATA_SYMBOL = "GC=F"
MARKET_NAME = "COMEX Gold Futures"

CHART_TIMEFRAMES = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1H": "1H",
    "4H": "4H",
    "1D": "D",
}

TREND_DISPLAY_ORDER = [
    ("1D", "D"),
    ("4H", "4H"),
    ("1H", "1H"),
    ("15m", "15m"),
    ("5m", "5m"),
    ("1m", "1m"),
]

DEFAULT_CHART_TF = "15m"

# Current V1 logic considers a zone "near" at 0.5%.
TRADE_ZONE_TOLERANCE_PCT = 0.5


# ---------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------

st.markdown(
    """
    <style>
        .block-container {
            max-width: 1550px;
            padding-top: 1.1rem;
            padding-bottom: 3rem;
        }

        [data-testid="stMetric"] {
            border: 1px solid rgba(128, 128, 128, 0.22);
            border-radius: 12px;
            padding: 12px 14px;
            background: rgba(128, 128, 128, 0.035);
        }

        .tp-eyebrow {
            font-size: 0.78rem;
            letter-spacing: 0.09em;
            font-weight: 700;
            opacity: 0.62;
            margin-bottom: 0.15rem;
        }

        .tp-title {
            font-size: 2.15rem;
            line-height: 1.1;
            font-weight: 800;
            margin-bottom: 0.15rem;
        }

        .tp-subtitle {
            font-size: 0.93rem;
            opacity: 0.68;
            margin-bottom: 0.25rem;
        }

        .tp-section {
            font-size: 1.18rem;
            font-weight: 750;
            margin-top: 0.25rem;
            margin-bottom: 0.5rem;
        }

        .tp-panel {
            border: 1px solid rgba(128, 128, 128, 0.22);
            border-radius: 14px;
            padding: 16px;
            background: rgba(128, 128, 128, 0.025);
            margin-bottom: 10px;
        }

        .tp-small {
            font-size: 0.82rem;
            opacity: 0.68;
        }

        .tp-zone-title {
            font-weight: 750;
            margin-bottom: 3px;
        }

        .tp-status-big {
            font-size: 1.28rem;
            font-weight: 800;
        }

        div[data-testid="stButton"] > button {
            border-radius: 10px;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.35rem;
        }

        .stTabs [data-baseweb="tab"] {
            border-radius: 8px 8px 0 0;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------

def safe_float(value, default=None):
    try:
        if value is None:
            return default
        value = float(value)
        if np.isnan(value):
            return default
        return value
    except Exception:
        return default


def money(value):
    value = safe_float(value)
    if value is None:
        return "—"
    return f"${value:,.2f}"


def points(value):
    value = safe_float(value)
    if value is None:
        return "—"
    return f"{value:,.2f} pts"


def pct(value):
    value = safe_float(value)
    if value is None:
        return "—"
    return f"{value:.1f}%"


def trend_icon(trend):
    if trend == "bullish":
        return "🟢"
    if trend == "bearish":
        return "🔴"
    if trend == "neutral":
        return "🟡"
    return "⚪"


def trend_label(trend):
    if not trend or trend == "no_data":
        return "NO DATA"
    return str(trend).upper()


def zone_mid(zone):
    return (float(zone["upper_bound"]) + float(zone["lower_bound"])) / 2.0


def zone_width(zone):
    return abs(float(zone["upper_bound"]) - float(zone["lower_bound"]))


def distance_to_zone(price, zone):
    """
    Distance from price to the nearest edge of the zone.
    Returns 0 when price is already inside the zone.
    """
    if price is None or zone is None:
        return None

    lower = float(zone["lower_bound"])
    upper = float(zone["upper_bound"])

    if lower <= price <= upper:
        return 0.0

    if price < lower:
        return lower - price

    return price - upper


def distance_pct_to_zone(price, zone):
    d = distance_to_zone(price, zone)
    if d is None or not price:
        return None
    return (d / price) * 100.0


def choose_best_demand(price, zones):
    """
    For a demand watch zone, prefer the closest zone at or below price.
    If price is inside a zone, that zone naturally wins.
    """
    if not zones or price is None:
        return None

    candidates = []

    for zone in zones:
        lower = float(zone["lower_bound"])
        upper = float(zone["upper_bound"])

        # Demand far above price is not the primary pullback zone we want.
        if lower > price:
            continue

        distance = distance_to_zone(price, zone)
        strength = safe_float(zone.get("strength"), 0) or 0

        candidates.append((distance, -strength, zone))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def choose_best_supply(price, zones):
    """
    For a supply watch zone, prefer the closest zone at or above price.
    """
    if not zones or price is None:
        return None

    candidates = []

    for zone in zones:
        lower = float(zone["lower_bound"])
        upper = float(zone["upper_bound"])

        # Supply far below price is not the primary rally zone we want.
        if upper < price:
            continue

        distance = distance_to_zone(price, zone)
        strength = safe_float(zone.get("strength"), 0) or 0

        candidates.append((distance, -strength, zone))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def resample_30m(df):
    """
    Build a temporary 30-minute chart from stored 15-minute candles.

    V2.1 only:
    The data engine does not currently persist 30m candles.
    A later data-engine milestone will make 30m a native timeframe.
    """
    if df is None or len(df) == 0:
        return None

    working = df.copy()

    if not isinstance(working.index, pd.DatetimeIndex):
        working.index = pd.to_datetime(working.index, utc=True)

    result = (
        working.resample("30min")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna(subset=["open", "high", "low", "close"])
    )

    return result


@st.cache_data(ttl=20, show_spinner=False)
def get_chart_data(display_tf, limit=240):
    db_tf = CHART_TIMEFRAMES[display_tf]

    if display_tf == "30m":
        raw = load_data("15m", limit=limit * 2 + 20)
        return resample_30m(raw)

    return load_data(db_tf, limit=limit)


@st.cache_data(ttl=20, show_spinner=False)
def get_zone_snapshot(timeframe="1H", limit=350):
    df = load_data(timeframe, limit=limit)

    if df is None or len(df) < 15:
        return None, [], []

    supply = detect_supply_zones(df)
    demand = detect_demand_zones(df)

    return df, supply, demand


def get_latest_timestamp():
    """
    Find the newest stored candle timestamp.
    """
    for tf in ["1m", "5m", "15m", "1H", "4H", "D"]:
        try:
            df = load_data(tf, limit=1)
            if df is not None and len(df) > 0:
                ts = pd.Timestamp(df.index[-1])
                if ts.tzinfo is None:
                    ts = ts.tz_localize("UTC")
                return ts
        except Exception:
            continue

    return None


def data_health(latest_ts):
    """
    V2.1 health indicator.

    Yahoo Finance is not a true exchange-direct real-time feed.
    Therefore the UI uses CONNECTED/STALE rather than claiming
    exchange-level LIVE data.
    """
    if latest_ts is None:
        return "DISCONNECTED", None

    now = pd.Timestamp.now(tz="UTC")
    age_minutes = max(0.0, (now - latest_ts).total_seconds() / 60.0)

    # Current Yahoo intraday data may be delayed.
    if age_minutes <= 45:
        return "CONNECTED", age_minutes

    return "STALE", age_minutes


def get_news_state():
    try:
        warning, level = generate_news_warning()
        return warning, level
    except Exception:
        return "News status unavailable", "UNKNOWN"


def build_current_snapshot():
    """
    Build the V2.1 dashboard snapshot using the EXISTING engines.

    This is intentionally not yet the final canonical setup object.
    That will be introduced when the setup state machine and upgraded
    trade engine are built.
    """
    current_price = get_current_price()

    try:
        trends = get_trends()
    except Exception:
        trends = {}

    try:
        direction, alignment = calculate_alignment(trends)
    except Exception:
        direction, alignment = "neutral", 0

    try:
        zone_df, supply, demand = get_zone_snapshot("1H", 350)
    except Exception:
        zone_df, supply, demand = None, [], []

    if current_price is None and zone_df is not None and len(zone_df) > 0:
        current_price = safe_float(zone_df["close"].iloc[-1])

    best_demand = choose_best_demand(current_price, demand)
    best_supply = choose_best_supply(current_price, supply)

    near_demand = []
    near_supply = []

    if current_price is not None:
        near_demand = [
            z
            for z in demand
            if is_price_near_zone(
                current_price,
                z,
                TRADE_ZONE_TOLERANCE_PCT,
            )
        ]

        near_supply = [
            z
            for z in supply
            if is_price_near_zone(
                current_price,
                z,
                TRADE_ZONE_TOLERANCE_PCT,
            )
        ]

    trade = None
    status = "NO TRADE"
    status_reason = "Price is not at a qualifying V1 zone."

    # Preserve existing V1 signal logic for now.
    # This will be replaced by the V2 setup state machine.
    if alignment < 60:
        status = "NO TRADE"
        status_reason = (
            f"Multi-timeframe alignment is {alignment:.0f}%, "
            "below the current 60% V1 threshold."
        )

    elif direction == "bullish" and near_demand:
        zone = near_demand[-1]
        entry = current_price
        stop = float(zone["lower_bound"]) * 0.998
        risk = entry - stop if entry is not None else None
        target = entry + (risk * 3.0) if risk and risk > 0 else None
        grade = grade_setup(alignment, zone.get("strength", 0))

        trade = {
            "direction": "LONG",
            "entry": entry,
            "stop": stop,
            "target_1": target,
            "target_2": None,
            "target_3": None,
            "rr": 3.0 if target is not None else None,
            "grade": grade,
            "zone": zone,
            "zone_type": "demand",
            "timeframe": "1H",
            "alignment": alignment,
        }

        status = "TRADE AVAILABLE"
        status_reason = (
            "Existing V1 logic sees bullish alignment and price near "
            "a detected 1H demand zone."
        )

    elif direction == "bearish" and near_supply:
        zone = near_supply[-1]
        entry = current_price
        stop = float(zone["upper_bound"]) * 1.002
        risk = stop - entry if entry is not None else None
        target = entry - (risk * 3.0) if risk and risk > 0 else None
        grade = grade_setup(alignment, zone.get("strength", 0))

        trade = {
            "direction": "SHORT",
            "entry": entry,
            "stop": stop,
            "target_1": target,
            "target_2": None,
            "target_3": None,
            "rr": 3.0 if target is not None else None,
            "grade": grade,
            "zone": zone,
            "zone_type": "supply",
            "timeframe": "1H",
            "alignment": alignment,
        }

        status = "TRADE AVAILABLE"
        status_reason = (
            "Existing V1 logic sees bearish alignment and price near "
            "a detected 1H supply zone."
        )

    else:
        if direction == "bullish" and best_demand:
            status = "WATCHING LONG"
            status_reason = (
                "Bullish bias is present. Waiting for price to reach "
                "the best nearby 1H demand zone."
            )

        elif direction == "bearish" and best_supply:
            status = "WATCHING SHORT"
            status_reason = (
                "Bearish bias is present. Waiting for price to reach "
                "the best nearby 1H supply zone."
            )

        elif direction == "neutral":
            status = "NO TRADE"
            status_reason = "Current timeframe voting does not produce a directional majority."

    latest_ts = get_latest_timestamp()
    health, age_minutes = data_health(latest_ts)
    news_warning, news_level = get_news_state()

    return {
        "price": current_price,
        "trends": trends,
        "direction": direction,
        "alignment": alignment,
        "supply": supply,
        "demand": demand,
        "best_supply": best_supply,
        "best_demand": best_demand,
        "near_supply": near_supply,
        "near_demand": near_demand,
        "trade": trade,
        "status": status,
        "status_reason": status_reason,
        "latest_timestamp": latest_ts,
        "data_health": health,
        "data_age_minutes": age_minutes,
        "news_warning": news_warning,
        "news_level": news_level,
    }


def zone_grade(zone):
    if not zone:
        return "—"

    strength = safe_float(zone.get("strength"), 0) or 0

    if strength >= 90:
        return "A+"
    if strength >= 80:
        return "A"
    if strength >= 65:
        return "B"
    if strength >= 50:
        return "C"

    return "D"


def build_candlestick_chart(
    df,
    timeframe_label,
    supply_zones=None,
    demand_zones=None,
    trade=None,
):
    """
    Interactive Altair candlestick chart.

    V2.1 uses Altair because it is already installed with Streamlit.
    This replaces the static PNG chart from V1.
    """
    if df is None or len(df) < 2:
        return None

    data = df.copy().tail(220).reset_index()

    # Normalize timestamp column name.
    first_col = data.columns[0]
    if first_col != "timestamp":
        data = data.rename(columns={first_col: "timestamp"})

    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True)

    for col in ["open", "high", "low", "close", "volume"]:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")

    data = data.dropna(subset=["open", "high", "low", "close"])

    if len(data) < 2:
        return None

    data["direction"] = np.where(
        data["close"] >= data["open"],
        "Up",
        "Down",
    )

    price_min = float(data["low"].min())
    price_max = float(data["high"].max())

    price_range = max(price_max - price_min, 1.0)
    y_min = price_min - price_range * 0.04
    y_max = price_max + price_range * 0.04

    base = alt.Chart(data).encode(
        x=alt.X(
            "timestamp:T",
            axis=alt.Axis(
                title=None,
                format="%m/%d %H:%M",
                labelAngle=-35,
                labelOverlap=True,
            ),
        )
    )

    wicks = base.mark_rule().encode(
        y=alt.Y(
            "low:Q",
            scale=alt.Scale(domain=[y_min, y_max], zero=False),
            axis=alt.Axis(title="Price"),
        ),
        y2="high:Q",
        color=alt.Color(
            "direction:N",
            scale=alt.Scale(
                domain=["Up", "Down"],
                range=["#16a34a", "#dc2626"],
            ),
            legend=None,
        ),
        tooltip=[
            alt.Tooltip("timestamp:T", title="Time"),
            alt.Tooltip("open:Q", title="Open", format=",.2f"),
            alt.Tooltip("high:Q", title="High", format=",.2f"),
            alt.Tooltip("low:Q", title="Low", format=",.2f"),
            alt.Tooltip("close:Q", title="Close", format=",.2f"),
            alt.Tooltip("volume:Q", title="Volume", format=",.0f"),
        ],
    )

    bodies = base.mark_bar(size=7).encode(
        y=alt.Y(
            "open:Q",
            scale=alt.Scale(domain=[y_min, y_max], zero=False),
        ),
        y2="close:Q",
        color=alt.Color(
            "direction:N",
            scale=alt.Scale(
                domain=["Up", "Down"],
                range=["#16a34a", "#dc2626"],
            ),
            legend=None,
        ),
        tooltip=[
            alt.Tooltip("timestamp:T", title="Time"),
            alt.Tooltip("open:Q", title="Open", format=",.2f"),
            alt.Tooltip("high:Q", title="High", format=",.2f"),
            alt.Tooltip("low:Q", title="Low", format=",.2f"),
            alt.Tooltip("close:Q", title="Close", format=",.2f"),
            alt.Tooltip("volume:Q", title="Volume", format=",.0f"),
        ],
    )

    chart = wicks + bodies

    # Only show the most relevant zones to avoid clutter.
    zone_rows = []

    if supply_zones:
        for zone in supply_zones[:3]:
            zone_rows.append(
                {
                    "lower": float(zone["lower_bound"]),
                    "upper": float(zone["upper_bound"]),
                    "zone_type": "Supply",
                }
            )

    if demand_zones:
        for zone in demand_zones[:3]:
            zone_rows.append(
                {
                    "lower": float(zone["lower_bound"]),
                    "upper": float(zone["upper_bound"]),
                    "zone_type": "Demand",
                }
            )

    if zone_rows:
        zone_df = pd.DataFrame(zone_rows)

        zone_layer = (
            alt.Chart(zone_df)
            .mark_rect(opacity=0.10)
            .encode(
                y=alt.Y(
                    "lower:Q",
                    scale=alt.Scale(domain=[y_min, y_max], zero=False),
                ),
                y2="upper:Q",
                color=alt.Color(
                    "zone_type:N",
                    scale=alt.Scale(
                        domain=["Supply", "Demand"],
                        range=["#dc2626", "#16a34a"],
                    ),
                    legend=alt.Legend(
                        title="Zones",
                        orient="top",
                    ),
                ),
            )
        )

        chart = chart + zone_layer

    # Current price line.
    last_price = safe_float(data["close"].iloc[-1])

    if last_price is not None:
        current_price_df = pd.DataFrame(
            {
                "price": [last_price],
                "label": [f"Current {last_price:,.2f}"],
            }
        )

        current_line = (
            alt.Chart(current_price_df)
            .mark_rule(
                color="#2563eb",
                strokeDash=[5, 4],
                strokeWidth=1.2,
            )
            .encode(
                y=alt.Y(
                    "price:Q",
                    scale=alt.Scale(domain=[y_min, y_max], zero=False),
                )
            )
        )

        chart = chart + current_line

    # Existing V1 trade plan.
    if trade:
        trade_levels = []

        if trade.get("entry") is not None:
            trade_levels.append(
                {
                    "price": float(trade["entry"]),
                    "label": f"{trade['direction']} ENTRY",
                    "level_type": "Entry",
                }
            )

        if trade.get("stop") is not None:
            trade_levels.append(
                {
                    "price": float(trade["stop"]),
                    "label": "STOP",
                    "level_type": "Stop",
                }
            )

        if trade.get("target_1") is not None:
            trade_levels.append(
                {
                    "price": float(trade["target_1"]),
                    "label": "TARGET",
                    "level_type": "Target",
                }
            )

        if trade_levels:
            levels_df = pd.DataFrame(trade_levels)

            trade_lines = (
                alt.Chart(levels_df)
                .mark_rule(strokeWidth=1.8)
                .encode(
                    y=alt.Y(
                        "price:Q",
                        scale=alt.Scale(domain=[y_min, y_max], zero=False),
                    ),
                    color=alt.Color(
                        "level_type:N",
                        scale=alt.Scale(
                            domain=["Entry", "Stop", "Target"],
                            range=["#2563eb", "#dc2626", "#16a34a"],
                        ),
                        legend=alt.Legend(
                            title="Trade",
                            orient="top",
                        ),
                    ),
                    tooltip=[
                        alt.Tooltip("label:N", title="Level"),
                        alt.Tooltip("price:Q", title="Price", format=",.2f"),
                    ],
                )
            )

            chart = chart + trade_lines

    chart = (
        chart.properties(
            height=570,
            title=f"{DISPLAY_SYMBOL} • {MARKET_NAME} • {timeframe_label}",
        )
        .interactive()
        .configure_view(strokeOpacity=0)
        .configure_axis(
            gridColor="#888888",
            gridOpacity=0.10,
        )
        .configure_title(
            anchor="start",
            fontSize=16,
        )
    )

    return chart


def get_relevant_chart_zones(snapshot, chart_price):
    """
    Pick a few relevant zones for the chart rather than drawing every
    historical zone.
    """
    supply = snapshot.get("supply", [])
    demand = snapshot.get("demand", [])

    supply_candidates = []
    for z in supply:
        if chart_price is None:
            continue
        if float(z["upper_bound"]) >= chart_price:
            supply_candidates.append(z)

    demand_candidates = []
    for z in demand:
        if chart_price is None:
            continue
        if float(z["lower_bound"]) <= chart_price:
            demand_candidates.append(z)

    supply_candidates = sorted(
        supply_candidates,
        key=lambda z: distance_to_zone(chart_price, z),
    )[:3]

    demand_candidates = sorted(
        demand_candidates,
        key=lambda z: distance_to_zone(chart_price, z),
    )[:3]

    return supply_candidates, demand_candidates


def render_zone_card(title, zone, price, zone_type):
    if not zone:
        st.markdown(
            f"""
            <div class="tp-panel">
                <div class="tp-zone-title">{title}</div>
                <div class="tp-small">No qualifying {zone_type.lower()} zone found.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    lower = float(zone["lower_bound"])
    upper = float(zone["upper_bound"])
    strength = safe_float(zone.get("strength"), 0) or 0
    distance = distance_to_zone(price, zone)
    distance_pct = distance_pct_to_zone(price, zone)

    st.markdown(
        f"""
        <div class="tp-panel">
            <div class="tp-zone-title">{title}</div>
            <div style="font-size:1.08rem;font-weight:750;">
                {money(lower)} – {money(upper)}
            </div>
            <div class="tp-small">
                Grade {zone_grade(zone)} • Strength {strength:.0f}/100
                • Distance {points(distance)}
                ({pct(distance_pct)})
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_setup_checklist(snapshot):
    """
    V2.1 checklist based only on information the CURRENT engines
    can actually prove.

    We intentionally do not mark future V2 confirmation rules as
    complete because those engines do not exist yet.
    """
    direction = snapshot["direction"]
    alignment = snapshot["alignment"]
    price = snapshot["price"]

    if direction == "bullish":
        watch_zone = snapshot["best_demand"]
        zone_name = "Qualified 1H demand identified"
        price_condition = bool(snapshot["near_demand"])
    elif direction == "bearish":
        watch_zone = snapshot["best_supply"]
        zone_name = "Qualified 1H supply identified"
        price_condition = bool(snapshot["near_supply"])
    else:
        watch_zone = None
        zone_name = "Directional watch zone identified"
        price_condition = False

    checks = [
        (
            alignment >= 60,
            f"Multi-timeframe alignment ≥ 60% ({alignment:.0f}%)",
        ),
        (
            direction in ("bullish", "bearish"),
            f"Directional bias identified ({direction.upper()})",
        ),
        (
            watch_zone is not None,
            zone_name,
        ),
        (
            price_condition,
            "Price is near the qualifying zone",
        ),
        (
            False,
            "V2 lower-timeframe confirmation",
        ),
        (
            False,
            "V2 structural entry trigger",
        ),
        (
            False,
            "V2 risk rules validated",
        ),
    ]

    completed = sum(1 for done, _ in checks if done)

    st.progress(completed / len(checks))
    st.caption(
        f"{completed}/{len(checks)} current/future setup conditions satisfied"
    )

    for done, label in checks:
        icon = "✅" if done else "⬜"
        st.write(f"{icon} {label}")


def render_trade_plan(snapshot):
    trade = snapshot["trade"]

    if not trade:
        st.markdown("### No confirmed V2 trade")

        if snapshot["direction"] == "bullish" and snapshot["best_demand"]:
            zone = snapshot["best_demand"]
            st.write(
                "Current plan: **watch for a LONG opportunity** if price "
                "returns to the selected demand zone."
            )
            st.metric(
                "Demand to Watch",
                f"{money(zone['lower_bound'])} – {money(zone['upper_bound'])}",
            )
            st.metric(
                "Distance",
                points(distance_to_zone(snapshot["price"], zone)),
            )

        elif snapshot["direction"] == "bearish" and snapshot["best_supply"]:
            zone = snapshot["best_supply"]
            st.write(
                "Current plan: **watch for a SHORT opportunity** if price "
                "returns to the selected supply zone."
            )
            st.metric(
                "Supply to Watch",
                f"{money(zone['lower_bound'])} – {money(zone['upper_bound'])}",
            )
            st.metric(
                "Distance",
                points(distance_to_zone(snapshot["price"], zone)),
            )

        else:
            st.write(
                "The current engines do not identify a directional trade "
                "location worth presenting."
            )

        st.info(
            "Entry, Stop, T1/T2/T3 and contract-dollar risk will become "
            "authoritative after the V2 setup and risk engines are built."
        )

        return

    direction = trade["direction"]

    if direction == "LONG":
        st.success(f"Existing V1 LONG signal • Grade {trade['grade']}")
    else:
        st.error(f"Existing V1 SHORT signal • Grade {trade['grade']}")

    c1, c2 = st.columns(2)
    c1.metric("Entry", money(trade["entry"]))
    c2.metric("Stop", money(trade["stop"]))

    c3, c4 = st.columns(2)
    c3.metric("Current Target", money(trade["target_1"]))
    c4.metric(
        "Current R:R",
        f"{trade['rr']:.1f}:1" if trade["rr"] else "—",
    )

    risk_points = None
    if trade["entry"] is not None and trade["stop"] is not None:
        risk_points = abs(trade["entry"] - trade["stop"])

    st.metric("Risk Distance", points(risk_points))

    st.warning(
        "This is still the existing V1 trade calculation. "
        "T1/T2/T3, structural stops, contract-dollar risk and historical "
        "probability will replace this logic in later V2 milestones."
    )

    if st.button(
        f"Log current {direction} signal",
        use_container_width=True,
        key="v2_log_trade",
    ):
        tid, tags = log_trade_with_dna(
            direction,
            trade["entry"],
            trade["stop"],
            trade["target_1"],
            trade["rr"],
            trade["grade"],
            trade["alignment"],
            trade["zone_type"],
            trade["timeframe"],
        )
        st.success(
            f"Trade #{tid} logged. Tags: {', '.join(tags)}"
        )


# ---------------------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------------------

if "chart_tf" not in st.session_state:
    st.session_state.chart_tf = DEFAULT_CHART_TF


# ---------------------------------------------------------------------
# BUILD SNAPSHOT
# ---------------------------------------------------------------------

with st.spinner("Loading Gold market snapshot..."):
    try:
        snapshot = build_current_snapshot()
    except Exception as exc:
        st.error(f"Unable to build market snapshot: {exc}")
        st.stop()


# ---------------------------------------------------------------------
# HEADER
# ---------------------------------------------------------------------

header_left, header_right = st.columns([5.2, 1.8])

with header_left:
    st.markdown(
        f"""
        <div class="tp-eyebrow">{APP_NAME.upper()}</div>
        <div class="tp-title">🥇 {COACH_NAME}</div>
        <div class="tp-subtitle">
            {DISPLAY_SYMBOL} • {MARKET_NAME} • Data: {get_data_source_name()}
        </div>
        """,
        unsafe_allow_html=True,
    )

with header_right:
    h1, h2 = st.columns(2)

    h1.metric(
        "Gold Price",
        money(snapshot["price"]),
    )

    health = snapshot["data_health"]

    if health == "CONNECTED":
        health_display = "🟢 CONNECTED"
    elif health == "STALE":
        health_display = "🟠 STALE"
    else:
        health_display = "🔴 DISCONNECTED"

    h2.metric(
        "Data",
        health_display,
    )

if snapshot["latest_timestamp"] is not None:
    local_ts = snapshot["latest_timestamp"]

    try:
        local_ts = local_ts.tz_convert("America/Los_Angeles")
    except Exception:
        pass

    st.caption(
        f"Latest stored candle: "
        f"{local_ts.strftime('%Y-%m-%d %H:%M:%S %Z')} "
        f"• Yahoo data may be delayed."
    )
else:
    st.caption("No stored candle timestamp available.")


# ---------------------------------------------------------------------
# TOP ACTION BAR
# ---------------------------------------------------------------------

action_left, action_mid, action_right = st.columns([1.2, 4.8, 1.2])

with action_left:
    if st.button(
        "🔄 Refresh Market Data",
        use_container_width=True,
        type="primary",
    ):
        with st.spinner("Refreshing GC=F market data..."):
            success = fetch_latest_data()

        st.cache_data.clear()

        if success:
            st.success("Market data refreshed.")
        else:
            st.error("Market-data refresh failed.")

        st.rerun()

with action_mid:
    news_level = snapshot["news_level"]
    news_warning = snapshot["news_warning"]

    if news_level == "HIGH":
        st.error(f"🔴 Event Risk: {news_warning}")
    elif news_level == "MEDIUM":
        st.warning(f"🟠 Event Risk: {news_warning}")
    elif news_level == "UNKNOWN":
        st.info("Economic-event status unavailable.")
    else:
        st.success("🟢 No major event warning from the current news engine.")

with action_right:
    st.caption(
        f"Dashboard refreshed\n{datetime.now().strftime('%H:%M:%S')}"
    )


# ---------------------------------------------------------------------
# MARKET STATUS
# ---------------------------------------------------------------------

st.divider()

m1, m2, m3, m4, m5 = st.columns(5)

bias_text = snapshot["direction"].upper()
status_text = snapshot["status"]

m1.metric("Market Bias", bias_text)
m2.metric("Alignment", f"{snapshot['alignment']:.0f}%")
m3.metric("Trade Status", status_text)

if snapshot["trade"]:
    m4.metric("Setup Grade", snapshot["trade"]["grade"])
else:
    m4.metric("Setup Grade", "—")

# Do NOT invent probability.
m5.metric("Historical Probability", "—")
m5.caption("Backtest-derived probability coming in V2")

st.caption(snapshot["status_reason"])


# ---------------------------------------------------------------------
# MAIN TABS
# ---------------------------------------------------------------------

dashboard_tab, journal_tab, stats_tab, backtest_tab, system_tab = st.tabs(
    [
        "📊 Dashboard",
        "📝 Journal",
        "📈 Stats",
        "🧪 Backtest",
        "⚙️ System",
    ]
)


# =====================================================================
# DASHBOARD TAB
# =====================================================================

with dashboard_tab:

    # -------------------------------------------------------------
    # TIMEFRAME SELECTOR
    # -------------------------------------------------------------

    st.markdown(
        '<div class="tp-section">Live Market Chart</div>',
        unsafe_allow_html=True,
    )

    tf_cols = st.columns(len(CHART_TIMEFRAMES))

    for index, display_tf in enumerate(CHART_TIMEFRAMES.keys()):
        button_type = (
            "primary"
            if st.session_state.chart_tf == display_tf
            else "secondary"
        )

        if tf_cols[index].button(
            display_tf,
            use_container_width=True,
            type=button_type,
            key=f"tf_{display_tf}",
        ):
            st.session_state.chart_tf = display_tf
            st.rerun()

    # -------------------------------------------------------------
    # CHART + RIGHT PANEL
    # -------------------------------------------------------------

    chart_col, side_col = st.columns([3.35, 1.15], gap="large")

    with chart_col:
        selected_tf = st.session_state.chart_tf

        try:
            chart_df = get_chart_data(selected_tf, 240)

            if chart_df is not None and len(chart_df) >= 5:
                chart_price = safe_float(chart_df["close"].iloc[-1])

                chart_supply, chart_demand = get_relevant_chart_zones(
                    snapshot,
                    chart_price,
                )

                chart = build_candlestick_chart(
                    chart_df,
                    selected_tf,
                    supply_zones=chart_supply,
                    demand_zones=chart_demand,
                    trade=snapshot["trade"],
                )

                if chart is not None:
                    st.altair_chart(
                        chart,
                        use_container_width=True,
                    )
                else:
                    st.warning(
                        "Chart data loaded but could not be rendered."
                    )

                first_ts = pd.Timestamp(chart_df.index[0])
                last_ts = pd.Timestamp(chart_df.index[-1])

                c1, c2, c3, c4 = st.columns(4)
                c1.metric(
                    "Chart Open",
                    money(chart_df["open"].iloc[-1]),
                )
                c2.metric(
                    "Chart High",
                    money(chart_df["high"].iloc[-1]),
                )
                c3.metric(
                    "Chart Low",
                    money(chart_df["low"].iloc[-1]),
                )
                c4.metric(
                    "Chart Close",
                    money(chart_df["close"].iloc[-1]),
                )

                st.caption(
                    f"{len(chart_df):,} candles loaded • "
                    f"{first_ts} → {last_ts}"
                )

                if selected_tf == "30m":
                    st.caption(
                        "30m candles are temporarily resampled from stored "
                        "15m data in V2.1."
                    )

            else:
                st.warning(
                    f"Not enough {selected_tf} data is currently stored."
                )

        except Exception as exc:
            st.error(f"Chart error: {exc}")

    with side_col:
        st.markdown("### Current Plan")

        if snapshot["status"] == "TRADE AVAILABLE":
            if snapshot["trade"]["direction"] == "LONG":
                st.success("🟢 LONG AVAILABLE")
            else:
                st.error("🔴 SHORT AVAILABLE")

        elif snapshot["status"] == "WATCHING LONG":
            st.info("🟢 WATCHING LONG")

        elif snapshot["status"] == "WATCHING SHORT":
            st.info("🔴 WATCHING SHORT")

        else:
            st.warning("⚪ NO TRADE")

        st.write(snapshot["status_reason"])

        st.divider()

        if snapshot["direction"] == "bullish":
            render_zone_card(
                "Primary Zone to Watch",
                snapshot["best_demand"],
                snapshot["price"],
                "Demand",
            )

        elif snapshot["direction"] == "bearish":
            render_zone_card(
                "Primary Zone to Watch",
                snapshot["best_supply"],
                snapshot["price"],
                "Supply",
            )

        else:
            render_zone_card(
                "Nearest Demand",
                snapshot["best_demand"],
                snapshot["price"],
                "Demand",
            )

        st.markdown("### Probability")
        st.metric("Historical Win Probability", "—")
        st.caption(
            "Not calculated yet. V2 will derive this from comparable "
            "historical setups and display sample size."
        )

    # -------------------------------------------------------------
    # WATCH ZONES
    # -------------------------------------------------------------

    st.divider()
    st.markdown(
        '<div class="tp-section">Zones to Watch</div>',
        unsafe_allow_html=True,
    )

    demand_col, supply_col = st.columns(2, gap="large")

    with demand_col:
        render_zone_card(
            "🟢 Best Demand",
            snapshot["best_demand"],
            snapshot["price"],
            "Demand",
        )

        if snapshot["best_demand"]:
            st.caption(
                "Current V2.1 selection: closest detected 1H demand "
                "at/below current price, with strength used as a tie-breaker."
            )

    with supply_col:
        render_zone_card(
            "🔴 Best Supply",
            snapshot["best_supply"],
            snapshot["price"],
            "Supply",
        )

        if snapshot["best_supply"]:
            st.caption(
                "Current V2.1 selection: closest detected 1H supply "
                "at/above current price, with strength used as a tie-breaker."
            )

    # -------------------------------------------------------------
    # MARKET STRUCTURE / TIMEFRAME VOTING
    # -------------------------------------------------------------

    st.divider()
    st.markdown(
        '<div class="tp-section">Multi-Timeframe Market Context</div>',
        unsafe_allow_html=True,
    )

    trend_cols = st.columns(len(TREND_DISPLAY_ORDER))

    for index, (label, key) in enumerate(TREND_DISPLAY_ORDER):
        trend = snapshot["trends"].get(key, "no_data")

        trend_cols[index].metric(
            label,
            f"{trend_icon(trend)} {trend_label(trend)}",
        )

    st.caption(
        "V2.1 is displaying the existing trend engine's directional "
        "classification. BOS/CHoCH and richer market-structure states "
        "will be added in a later milestone."
    )

    # -------------------------------------------------------------
    # SETUP CHECKLIST + TRADE PLAN
    # -------------------------------------------------------------

    st.divider()

    checklist_col, plan_col = st.columns([1.15, 1], gap="large")

    with checklist_col:
        st.markdown(
            '<div class="tp-section">Setup Checklist</div>',
            unsafe_allow_html=True,
        )
        render_setup_checklist(snapshot)

    with plan_col:
        st.markdown(
            '<div class="tp-section">Trade / Watch Plan</div>',
            unsafe_allow_html=True,
        )
        render_trade_plan(snapshot)

    # -------------------------------------------------------------
    # PROFESSOR PLACEHOLDER
    # -------------------------------------------------------------

    st.divider()

    professor_col, engine_col = st.columns([1.35, 1], gap="large")

    with professor_col:
        st.markdown(
            '<div class="tp-section">Professor</div>',
            unsafe_allow_html=True,
        )

        st.info(
            "Professor integration is intentionally not connected in V2.1. "
            "The final Professor will consume the same structured setup "
            "data shown on this dashboard rather than inventing trade levels."
        )

        professor_prompt = st.text_input(
            "Ask about the current market",
            placeholder="Example: Why are we waiting for this zone?",
            disabled=True,
        )

        st.caption(
            "Coming milestone: What is Gold doing? • Why this zone? • "
            "Why no trade? • What confirms entry? • Explain the stop/targets."
        )

    with engine_col:
        st.markdown(
            '<div class="tp-section">Current Engine Status</div>',
            unsafe_allow_html=True,
        )

        st.write("✅ Live/stored Gold market data")
        st.write("✅ Multi-timeframe trend voting")
        st.write("✅ Existing supply/demand detection")
        st.write("✅ Interactive multi-timeframe chart")
        st.write("✅ Basic watch-zone selection")
        st.write("🟡 Existing V1 trade calculation")
        st.write("⬜ V2 setup state machine")
        st.write("⬜ Structural entry/stop engine")
        st.write("⬜ T1 / T2 / T3 engine")
        st.write("⬜ Contract-dollar risk engine")
        st.write("⬜ Backtest-derived probability")
        st.write("⬜ Professor integration")


# =====================================================================
# JOURNAL TAB
# =====================================================================

with journal_tab:
    st.subheader("Trade Journal")

    try:
        trades_df = get_all_trades()

        if len(trades_df) > 0:
            for _, trade_row in trades_df.head(30).iterrows():
                outcome = str(trade_row["outcome"])

                if outcome == "WIN":
                    emoji = "🟢"
                elif outcome == "LOSS":
                    emoji = "🔴"
                elif outcome == "BREAKEVEN":
                    emoji = "⚪"
                else:
                    emoji = "🟡"

                title = (
                    f"{emoji} #{trade_row['id']}: "
                    f"{trade_row['direction']} @ "
                    f"{money(trade_row['entry'])} | "
                    f"Grade {trade_row['grade']} | {outcome}"
                )

                with st.expander(title):
                    c1, c2 = st.columns(2)

                    with c1:
                        st.write(
                            f"Entry: {money(trade_row['entry'])}"
                        )
                        st.write(
                            f"Stop: {money(trade_row['stop'])}"
                        )
                        st.write(
                            f"Target: {money(trade_row['target'])}"
                        )

                    with c2:
                        st.write(f"Outcome: {outcome}")

                        if (
                            trade_row["exit_price"]
                            and str(trade_row["exit_price"]) != "nan"
                        ):
                            st.write(
                                f"Exit: {money(trade_row['exit_price'])}"
                            )

                        if (
                            trade_row["pnl"]
                            and str(trade_row["pnl"]) != "nan"
                        ):
                            st.write(
                                f"P&L: {money(trade_row['pnl'])}"
                            )

                    if outcome == "OPEN":
                        new_outcome = st.selectbox(
                            "Update Outcome",
                            [
                                "OPEN",
                                "WIN",
                                "LOSS",
                                "BREAKEVEN",
                            ],
                            key=f"journal_outcome_{trade_row['id']}",
                        )

                        exit_price = st.number_input(
                            "Exit Price",
                            value=float(trade_row["entry"]),
                            key=f"journal_exit_{trade_row['id']}",
                        )

                        if st.button(
                            f"Update Trade #{trade_row['id']}",
                            key=f"journal_update_{trade_row['id']}",
                        ):
                            if new_outcome != "OPEN":
                                update_outcome(
                                    trade_row["id"],
                                    new_outcome,
                                    exit_price,
                                )
                                st.rerun()

        else:
            st.info("No trades in the journal yet.")

    except Exception as exc:
        st.error(f"Error loading journal: {exc}")


# =====================================================================
# STATS TAB
# =====================================================================

with stats_tab:
    st.subheader("Performance Statistics")

    try:
        stats = calculate_statistics()

        if stats:
            c1, c2, c3, c4, c5 = st.columns(5)

            c1.metric(
                "Trades",
                stats["total_trades"],
            )
            c2.metric(
                "Win Rate",
                f"{stats['win_rate']}%",
            )
            c3.metric(
                "Profit Factor",
                f"{stats['profit_factor']}",
            )
            c4.metric(
                "Expectancy",
                money(stats["expectancy"]),
            )
            c5.metric(
                "Total P&L",
                money(stats["total_pnl"]),
            )

            st.divider()

            d1, d2, d3 = st.columns(3)

            with d1:
                st.write(f"Wins: {stats['wins']}")
                st.write(f"Losses: {stats['losses']}")
                st.write(f"Breakeven: {stats['breakeven']}")

            with d2:
                st.write(
                    f"Average Win: {money(stats['avg_win'])}"
                )
                st.write(
                    f"Average Loss: {money(stats['avg_loss'])}"
                )

            with d3:
                st.write(
                    f"Max Drawdown: {money(stats['max_drawdown'])}"
                )
                st.write(
                    f"Profit Factor: {stats['profit_factor']}"
                )

            try:
                dna_df = analyze_dna_performance()

                if len(dna_df) > 0:
                    st.divider()
                    st.subheader("Trade DNA Analysis")
                    st.dataframe(
                        dna_df,
                        use_container_width=True,
                    )
            except Exception:
                pass

        else:
            st.info(
                "No closed trades yet. Statistics will appear after "
                "trades complete."
            )

    except Exception as exc:
        st.error(f"Error loading statistics: {exc}")


# =====================================================================
# BACKTEST TAB
# =====================================================================

with backtest_tab:
    st.subheader("Historical Backtest")

    st.warning(
        "This is the existing V1 backtester. Its results should NOT yet "
        "be interpreted as the final V2 historical probability engine. "
        "We will later make live setup logic and backtest logic share "
        "the same deterministic strategy engine."
    )

    try:
        available_years = get_available_years()

        if available_years:
            st.success(
                f"Historical data available from "
                f"{available_years[0]} to {available_years[-1]}"
            )

            col1, col2, col3 = st.columns(3)

            with col1:
                selected_year = st.selectbox(
                    "Year",
                    ["All"]
                    + [str(y) for y in available_years],
                    key="v2_bt_year",
                )

                if selected_year != "All":
                    start_date = f"{selected_year}-01-01"
                    end_date = f"{selected_year}-12-31"
                else:
                    start_date = f"{available_years[0]}-01-01"
                    end_date = f"{available_years[-1]}-12-31"

            with col2:
                min_strength = st.slider(
                    "Minimum Zone Strength",
                    5,
                    80,
                    15,
                    key="v2_bt_strength",
                )

            with col3:
                use_trailing_stop = st.checkbox(
                    "Use Trailing Stop",
                    value=False,
                    key="v2_bt_trailing",
                )

            if st.button(
                "🚀 Run Existing Backtest",
                type="primary",
                use_container_width=True,
            ):
                with st.spinner("Running backtest..."):
                    result = run_backtest(
                        start_date=start_date,
                        end_date=end_date,
                        initial_capital=10000,
                        risk_per_trade=0.02,
                        zone_timeframe="D",
                        entry_timeframe="D",
                        trend_timeframe="D",
                        min_zone_strength=min_strength,
                        trend_mode="OR",
                        use_trailing_stop=use_trailing_stop,
                    )

                if (
                    result
                    and result["stats"]["total_trades"] > 0
                ):
                    result_stats = result["stats"]

                    r1, r2, r3, r4 = st.columns(4)

                    r1.metric(
                        "Trades",
                        result_stats["total_trades"],
                    )
                    r2.metric(
                        "Win Rate",
                        f"{result_stats['win_rate']:.1f}%",
                    )
                    r3.metric(
                        "Profit Factor",
                        f"{result_stats['profit_factor']:.2f}",
                    )
                    r4.metric(
                        "Return",
                        f"{result_stats['total_return']:.1f}%",
                    )

                    st.write(
                        f"Final capital: "
                        f"${result_stats['final_capital']:,.0f} "
                        f"• Max DD: "
                        f"{result_stats['max_drawdown']:.1f}%"
                    )

                else:
                    st.warning(
                        "No trades generated. Try a lower zone-strength "
                        "threshold or a broader date range."
                    )

        else:
            st.warning(
                "No historical data is currently available."
            )

    except Exception as exc:
        st.error(f"Backtest error: {exc}")


# =====================================================================
# SYSTEM TAB
# =====================================================================

with system_tab:
    st.subheader("System / Data Diagnostics")

    sys1, sys2, sys3 = st.columns(3)

    sys1.metric(
        "Application",
        "V2.1 Development",
    )

    sys2.metric(
        "Symbol",
        DATA_SYMBOL,
    )

    sys3.metric(
        "Data Health",
        snapshot["data_health"],
    )

    st.caption(
        "This local V2 build intentionally keeps the existing database "
        "schema and V1 engines while the dashboard is being upgraded."
    )

    st.divider()

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT timeframe, COUNT(*)
            FROM gold_ohlcv
            GROUP BY timeframe
            ORDER BY timeframe
            """
        )

        rows = cur.fetchall()

        if rows:
            st.write("### Database Rows")

            st.dataframe(
                pd.DataFrame(
                    rows,
                    columns=[
                        "Timeframe",
                        "Row Count",
                    ],
                ),
                use_container_width=True,
            )

        cur.execute(
            """
            SELECT timeframe, MAX(timestamp)
            FROM gold_ohlcv
            GROUP BY timeframe
            ORDER BY timeframe
            """
        )

        latest = cur.fetchall()

        if latest:
            st.write("### Latest Stored Timestamps")

            st.dataframe(
                pd.DataFrame(
                    latest,
                    columns=[
                        "Timeframe",
                        "Latest Timestamp",
                    ],
                ),
                use_container_width=True,
            )

        cur.close()
        conn.close()

    except Exception as exc:
        st.error(f"Database diagnostics error: {exc}")

    st.divider()

    st.write("### Current Economic Event Output")

    try:
        old_stdout = sys.stdout
        sys.stdout = StringIO()

        display_news_calendar()

        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        if output.strip():
            st.text(output)
        else:
            st.caption(
                "No text returned by the existing news calendar."
            )

    except Exception as exc:
        try:
            sys.stdout = old_stdout
        except Exception:
            pass

        st.caption(
            f"News calendar unavailable: {exc}"
        )

    st.divider()

    st.write("### V2 Roadmap")

    roadmap = pd.DataFrame(
        [
            ["V2.1", "Dashboard + interactive chart", "IN PROGRESS"],
            ["V2.2", "Market structure engine", "NEXT"],
            ["V2.3", "Zone engine V2", "PLANNED"],
            ["V2.4", "Setup state machine", "PLANNED"],
            ["V2.5", "Long/short trade plan engine", "PLANNED"],
            ["V2.6", "Contract risk/value engine", "PLANNED"],
            ["V2.7", "Backtest-derived probability", "PLANNED"],
            ["V2.8", "Professor integration", "PLANNED"],
            ["V2.9", "Multi-futures architecture", "PLANNED"],
        ],
        columns=[
            "Milestone",
            "Scope",
            "Status",
        ],
    )

    st.dataframe(
        roadmap,
        use_container_width=True,
        hide_index=True,
    )


# ---------------------------------------------------------------------
# FOOTER
# ---------------------------------------------------------------------

st.divider()

st.caption(
    "The Trading Pulse • Gold Trading Coach V2 Development • "
    "Educational market-analysis software • Not financial advice."
)