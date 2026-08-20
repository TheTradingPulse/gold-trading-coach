"""
THE TRADING PULSE
Gold Trading Coach V2.5.1 Dashboard

Rules:
- MarketState is the single source of truth.
- Dashboard never invents trade signals, entries, stops, targets, or probabilities.
- Higher-timeframe zones are context.
- Tactical zones are execution locations.
- Opposing-zone conflicts are surfaced.
- Charts show only decision-useful information.
- Professor consumes the same MarketState shown to the trader.
- GC is production instrument #1; UI is structured for future multi-symbol support.

IMPORTANT:
This source is intentionally ASCII-only to avoid Windows PowerShell / cp1252
encoding corruption.
"""

import sys
from datetime import datetime
from io import StringIO

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------
# PATHS / EXISTING ENGINES
# ---------------------------------------------------------------------

sys.path.insert(0, "core")
sys.path.insert(0, "analysis")

from streamlit_autorefresh import st_autorefresh

from database import get_connection
from market_state_builder import build_market_state, load_market_data
from live_data_engine import fetch_latest_data, get_data_source_name
from journal_engine import calculate_statistics, get_all_trades, update_outcome
from dna_engine import analyze_dna_performance
from news_engine import generate_news_warning, display_news_calendar
from backtest_engine import run_backtest, get_available_years


# ---------------------------------------------------------------------
# PAGE
# ---------------------------------------------------------------------

st.set_page_config(
    page_title="The Trading Pulse | Gold",
    page_icon="TP",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st_autorefresh(interval=60 * 1000, key="tp_auto_refresh")


# ---------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------

APP_NAME = "THE TRADING PULSE"
COACH_NAME = "GOLD TRADING COACH"
DISPLAY_SYMBOL = "GC"
MARKET_NAME = "COMEX GOLD FUTURES"
ACCENT = "#d7b45a"
ACCENT_SOFT = "#f0d98a"
BG = "#07090d"
PANEL = "#0d1118"
PANEL_2 = "#111722"
BORDER = "#242c39"
TEXT = "#f5f7fa"
MUTED = "#b3bdcb"
GREEN = "#22c55e"
RED = "#ef4444"
BLUE = "#3b82f6"
AMBER = "#f59e0b"

CHART_TIMEFRAMES = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1H": "1H",
    "4H": "4H",
    "1D": "D",
    "1W": "W",
}

TREND_DISPLAY_ORDER = [
    ("M", "M"),
    ("W", "W"),
    ("D", "D"),
    ("4H", "4H"),
    ("1H", "1H"),
    ("15m", "15m"),
    ("5m", "5m"),
    ("1m", "1m"),
]

DEFAULT_CHART_TF = "15m"


# ---------------------------------------------------------------------
# BRAND CSS
# ---------------------------------------------------------------------

st.markdown(
    f"""
    <style>
    :root {{
        --tp-bg: {BG};
        --tp-panel: {PANEL};
        --tp-panel2: {PANEL_2};
        --tp-border: {BORDER};
        --tp-text: {TEXT};
        --tp-muted: {MUTED};
        --tp-gold: {ACCENT};
        --tp-gold2: {ACCENT_SOFT};
        --tp-green: {GREEN};
        --tp-red: {RED};
    }}

    html, body, [class*="css"] {{
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
                     "Segoe UI", sans-serif;
    }}

    .stApp {{
        background:
            radial-gradient(circle at 15% 0%, rgba(215,180,90,.08), transparent 28rem),
            radial-gradient(circle at 85% 10%, rgba(59,130,246,.045), transparent 30rem),
            var(--tp-bg);
        color: var(--tp-text);
    }}

    [data-testid="stHeader"] {{
        background: rgba(7,9,13,.85);
    }}

    [data-testid="stToolbar"] {{
        right: 1rem;
    }}

    .block-container {{
        max-width: 1700px;
        padding-top: 1.25rem;
        padding-bottom: 4rem;
    }}

    hr {{
        border-color: rgba(255,255,255,.07) !important;
    }}

    .tp-topline {{
        height: 2px;
        width: 100%;
        background: linear-gradient(90deg, transparent, var(--tp-gold), transparent);
        opacity: .75;
        margin-bottom: 18px;
    }}

    .tp-brand-row {{
        display: flex;
        align-items: center;
        gap: 14px;
    }}

    .tp-mark {{
        width: 46px;
        height: 46px;
        border: 1px solid rgba(215,180,90,.55);
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: var(--tp-gold2);
        font-weight: 900;
        letter-spacing: -.06em;
        background: linear-gradient(145deg, rgba(215,180,90,.13), rgba(255,255,255,.015));
        box-shadow: 0 0 30px rgba(215,180,90,.08);
    }}

    .tp-eyebrow {{
        color: var(--tp-gold);
        font-size: .72rem;
        letter-spacing: .18em;
        font-weight: 850;
        text-transform: uppercase;
    }}

    .tp-title {{
        color: var(--tp-text);
        font-size: clamp(1.65rem, 2.3vw, 2.6rem);
        line-height: 1.02;
        font-weight: 900;
        letter-spacing: -.045em;
        margin-top: 3px;
    }}

    .tp-subtitle {{
        color: var(--tp-muted);
        font-size: .83rem;
        margin-top: 8px;
        letter-spacing: .025em;
    }}

    .tp-section-label {{
        color: var(--tp-gold);
        font-size: .68rem;
        font-weight: 850;
        letter-spacing: .16em;
        text-transform: uppercase;
        margin-bottom: 5px;
    }}

    .tp-section-title {{
        color: var(--tp-text);
        font-size: 1.22rem;
        font-weight: 850;
        letter-spacing: -.02em;
        margin-bottom: 12px;
    }}

    .tp-card {{
        border: 1px solid var(--tp-border);
        border-radius: 14px;
        background: linear-gradient(145deg, rgba(17,23,34,.96), rgba(10,14,20,.96));
        padding: 15px 16px;
        min-height: 102px;
        box-shadow: 0 10px 28px rgba(0,0,0,.16);
    }}

    .tp-card.gold {{
        border-color: rgba(215,180,90,.35);
        background: linear-gradient(145deg, rgba(215,180,90,.08), rgba(13,17,24,.96));
    }}

    .tp-card.red {{
        border-color: rgba(239,68,68,.32);
        background: linear-gradient(145deg, rgba(239,68,68,.07), rgba(13,17,24,.96));
    }}

    .tp-card.green {{
        border-color: rgba(34,197,94,.28);
        background: linear-gradient(145deg, rgba(34,197,94,.06), rgba(13,17,24,.96));
    }}

    .tp-kicker {{
        color: var(--tp-muted);
        font-size: .66rem;
        font-weight: 800;
        letter-spacing: .12em;
        text-transform: uppercase;
        margin-bottom: 7px;
    }}

    .tp-value {{
        color: var(--tp-text);
        font-size: 1.24rem;
        font-weight: 850;
        letter-spacing: -.025em;
        line-height: 1.1;
    }}

    .tp-value.gold {{
        color: var(--tp-gold2);
    }}

    .tp-detail {{
        color: var(--tp-muted);
        font-size: .76rem;
        line-height: 1.5;
        margin-top: 7px;
    }}

    .tp-status {{
        display: inline-flex;
        align-items: center;
        gap: 7px;
        border-radius: 999px;
        padding: 6px 10px;
        font-size: .68rem;
        font-weight: 850;
        letter-spacing: .08em;
        text-transform: uppercase;
        border: 1px solid var(--tp-border);
        background: rgba(255,255,255,.025);
    }}

    .tp-dot {{
        width: 7px;
        height: 7px;
        border-radius: 999px;
        display: inline-block;
    }}

    .tp-professor {{
        border: 1px solid rgba(215,180,90,.32);
        border-radius: 16px;
        padding: 18px;
        background:
            radial-gradient(circle at 0% 0%, rgba(215,180,90,.10), transparent 17rem),
            linear-gradient(145deg, rgba(17,23,34,.98), rgba(9,12,18,.98));
        box-shadow: 0 14px 40px rgba(0,0,0,.20);
    }}

    .tp-prof-title {{
        color: var(--tp-text);
        font-size: 1.08rem;
        font-weight: 900;
        letter-spacing: -.02em;
    }}

    .tp-prof-copy {{
        color: var(--tp-muted);
        font-size: .82rem;
        line-height: 1.55;
        margin-top: 6px;
    }}

    .tp-rule {{
        border-left: 2px solid rgba(215,180,90,.6);
        padding: 7px 0 7px 11px;
        color: #c9d0da;
        font-size: .79rem;
        margin: 6px 0;
    }}

    [data-testid="stMetric"] {{
        background: linear-gradient(145deg, rgba(17,23,34,.94), rgba(10,14,20,.94));
        border: 1px solid var(--tp-border);
        border-radius: 13px;
        padding: 13px 14px;
        box-shadow: 0 8px 24px rgba(0,0,0,.13);
    }}

    [data-testid="stMetricLabel"] {{
        color: var(--tp-muted);
        font-size: .72rem;
        letter-spacing: .04em;
    }}

    [data-testid="stMetricValue"] {{
        color: var(--tp-text);
        font-weight: 850;
        letter-spacing: -.025em;
    }}

    div[data-testid="stButton"] > button {{
        border-radius: 10px;
        border: 1px solid var(--tp-border);
        background: #0f141d;
        color: #d8dee8;
        font-weight: 750;
        transition: all .15s ease;
    }}

    div[data-testid="stButton"] > button:hover {{
        border-color: rgba(215,180,90,.55);
        color: var(--tp-gold2);
        transform: translateY(-1px);
    }}

    div[data-testid="stButton"] > button[kind="primary"] {{
        background: linear-gradient(135deg, #d7b45a, #a98635);
        color: #080a0d;
        border-color: #d7b45a;
        font-weight: 900;
    }}

    .stTabs [data-baseweb="tab-list"] {{
        gap: .35rem;
        background: rgba(13,17,24,.72);
        border: 1px solid var(--tp-border);
        border-radius: 12px;
        padding: 5px;
    }}

    .stTabs [data-baseweb="tab"] {{
        border-radius: 8px;
        color: var(--tp-muted);
        font-weight: 750;
    }}

    .stTabs [aria-selected="true"] {{
        color: var(--tp-gold2) !important;
        background: rgba(215,180,90,.08) !important;
    }}

    [data-testid="stDataFrame"] {{
        border: 1px solid var(--tp-border);
        border-radius: 12px;
        overflow: hidden;
    }}

    [data-testid="stAlert"] {{
        border-radius: 12px;
    }}

    .tp-footer {{
        color: #687386;
        text-align: center;
        font-size: .72rem;
        padding-top: 16px;
        letter-spacing: .02em;
    }}


    /* V2.5.1 premium cleanup */
    .tp-hero {{
        border: 1px solid rgba(255,255,255,.08);
        border-radius: 18px;
        padding: 16px 18px;
        background:
            radial-gradient(circle at 80% 10%, rgba(239,68,68,.11), transparent 20rem),
            linear-gradient(135deg, rgba(17,23,34,.98), rgba(7,9,13,.98));
        box-shadow: 0 18px 50px rgba(0,0,0,.22);
        margin-bottom: 14px;
    }}

    .tp-hero-copy {{
        color: #e7ebf1;
        font-size: .92rem;
        line-height: 1.55;
        margin-top: 5px;
    }}

    .tp-hero-tag {{
        color: #ef4444;
        font-size: .68rem;
        font-weight: 900;
        letter-spacing: .18em;
        text-transform: uppercase;
    }}

    .tp-trend-card {{
        min-height: 88px;
        border: 1px solid var(--tp-border);
        border-radius: 12px;
        padding: 11px 12px;
        background: linear-gradient(145deg, rgba(17,23,34,.97), rgba(9,12,18,.97));
        box-shadow: 0 8px 22px rgba(0,0,0,.15);
        overflow: hidden;
    }}

    .tp-trend-card.bullish {{ border-top: 2px solid rgba(34,197,94,.85); }}
    .tp-trend-card.bearish {{ border-top: 2px solid rgba(239,68,68,.85); }}
    .tp-trend-card.neutral {{ border-top: 2px solid rgba(245,158,11,.75); }}

    .tp-trend-tf {{
        color: #aeb8c6;
        font-size: .66rem;
        font-weight: 850;
        letter-spacing: .08em;
        text-transform: uppercase;
    }}

    .tp-trend-value {{
        color: #f5f7fa;
        font-size: .93rem;
        font-weight: 900;
        margin-top: 8px;
        white-space: nowrap;
    }}

    .tp-trend-value.bullish {{ color: #4ade80; }}
    .tp-trend-value.bearish {{ color: #fb7185; }}
    .tp-trend-value.neutral {{ color: #fbbf24; }}

    [data-testid="stCaptionContainer"],
    [data-testid="stMarkdownContainer"] p {{
        color: #b3bdcb;
    }}

    div[data-baseweb="input"] input:disabled {{
        color: #c7d0dc !important;
        -webkit-text-fill-color: #c7d0dc !important;
        opacity: 1 !important;
        background: #0c1119 !important;
    }}

    details {{
        border: 1px solid rgba(255,255,255,.08) !important;
        border-radius: 12px !important;
        background: rgba(13,17,24,.78) !important;
    }}

    @media (max-width: 900px) {{
        .block-container {{
            padding-left: .8rem;
            padding-right: .8rem;
        }}
    }}
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
    return "--" if value is None else f"${value:,.2f}"


def points(value):
    value = safe_float(value)
    return "--" if value is None else f"{value:,.2f} pts"


def trend_label(trend):
    if not trend or trend == "no_data":
        return "NO DATA"
    return str(trend).upper()


def trend_symbol(trend):
    if trend == "bullish":
        return "UP"
    if trend == "bearish":
        return "DOWN"
    if trend == "neutral":
        return "FLAT"
    return "--"


def trend_color(trend):
    if trend == "bullish":
        return GREEN
    if trend == "bearish":
        return RED
    if trend == "neutral":
        return AMBER
    return MUTED


def zone_dict(zone):
    if zone is None:
        return None
    if isinstance(zone, dict):
        return zone
    if hasattr(zone, "to_dict"):
        try:
            return zone.to_dict()
        except Exception:
            pass
    if hasattr(zone, "__dict__"):
        return dict(zone.__dict__)
    return None


def data_health(timestamp_value):
    if timestamp_value is None:
        return "DISCONNECTED", None
    try:
        ts = pd.Timestamp(timestamp_value)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        now = pd.Timestamp.now(tz="UTC")
        age_minutes = max(0.0, (now - ts).total_seconds() / 60.0)
        if age_minutes <= 45:
            return "CONNECTED", age_minutes
        return "STALE", age_minutes
    except Exception:
        return "UNKNOWN", None


def get_news_state():
    try:
        warning, level = generate_news_warning()
        return warning, level
    except Exception:
        return "Economic-event status unavailable.", "UNKNOWN"


def resample_30m(df):
    if df is None or len(df) == 0:
        return None
    working = df.copy()
    if not isinstance(working.index, pd.DatetimeIndex):
        working.index = pd.to_datetime(working.index, utc=True)
    return (
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


@st.cache_data(ttl=20, show_spinner=False)
def get_chart_data(display_tf, limit=260):
    db_tf = CHART_TIMEFRAMES[display_tf]
    if display_tf == "30m":
        raw = load_market_data("15m", limit=limit * 2 + 20)
        return resample_30m(raw)
    return load_market_data(db_tf, limit=limit)


@st.cache_resource(ttl=15, show_spinner=False)
def get_market_state():
    return build_market_state("GC")


def get_zone_model(state):
    return (state.professor_context or {}).get("zone_model", {})


def get_context_zone(state):
    return get_zone_model(state).get("context_zone")


def get_execution_zone(state):
    return get_zone_model(state).get("execution_zone")


def get_conflict_zone(state):
    return get_zone_model(state).get("opposing_conflict")


def zone_summary(zone):
    z = zone_dict(zone)
    if not z:
        return "No qualifying zone"
    return (
        f"{z.get('timeframe', '--')} {str(z.get('type', '')).upper()} | "
        f"{money(z.get('lower_bound'))} - {money(z.get('upper_bound'))}"
    )


def render_section(label, title):
    st.markdown(
        f"""
        <div class="tp-section-label">{label}</div>
        <div class="tp-section-title">{title}</div>
        """,
        unsafe_allow_html=True,
    )


def render_zone_card(title, zone, role, variant=""):
    z = zone_dict(zone)
    css_variant = f" {variant}" if variant else ""
    if not z:
        st.markdown(
            f"""
            <div class="tp-card{css_variant}">
                <div class="tp-kicker">{title}</div>
                <div class="tp-value">No qualifying zone</div>
                <div class="tp-detail">
                    MarketState has not selected a {role.lower()} zone.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    lower = safe_float(z.get("lower_bound"))
    upper = safe_float(z.get("upper_bound"))
    strength = safe_float(z.get("strength"), 0)
    distance = safe_float(z.get("distance_points"))
    distance_pct = safe_float(z.get("distance_percent"), 0)
    timeframe = z.get("timeframe", "--")
    zone_type = str(z.get("type", "")).upper()
    grade = z.get("grade", "--")
    width = upper - lower if upper is not None and lower is not None else None

    st.markdown(
        f"""
        <div class="tp-card{css_variant}">
            <div class="tp-kicker">{title}</div>
            <div class="tp-value">{money(lower)} - {money(upper)}</div>
            <div class="tp-detail">
                {timeframe} {zone_type} &nbsp;|&nbsp;
                Grade {grade} &nbsp;|&nbsp;
                Strength {strength:.0f}/100<br>
                Width {points(width)} &nbsp;|&nbsp;
                Distance {points(distance)} ({distance_pct:.3f}%)
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------
# CHART
# ---------------------------------------------------------------------

def build_candlestick_chart(df, timeframe_label, state):
    if df is None or len(df) < 2:
        return None

    data = df.copy().tail(220).reset_index()
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

    data["direction"] = np.where(data["close"] >= data["open"], "Up", "Down")

    price_min = float(data["low"].min())
    price_max = float(data["high"].max())
    price_range = max(price_max - price_min, 1.0)
    y_min = price_min - price_range * 0.045
    y_max = price_max + price_range * 0.045

    x_encoding = alt.X(
        "timestamp:T",
        axis=alt.Axis(
            title=None,
            format="%m/%d %H:%M",
            labelAngle=-35,
            labelOverlap=True,
            labelColor=MUTED,
            tickColor=BORDER,
            domainColor=BORDER,
        ),
    )

    y_encoding = alt.Y(
        "low:Q",
        scale=alt.Scale(domain=[y_min, y_max], zero=False),
        axis=alt.Axis(
            title=None,
            labelColor=MUTED,
            tickColor=BORDER,
            domainColor=BORDER,
            format=",.2f",
        ),
    )

    color_scale = alt.Scale(
        domain=["Up", "Down"],
        range=[GREEN, RED],
    )

    base = alt.Chart(data).encode(x=x_encoding)

    wicks = base.mark_rule(strokeWidth=1.1).encode(
        y=y_encoding,
        y2="high:Q",
        color=alt.Color("direction:N", scale=color_scale, legend=None),
        tooltip=[
            alt.Tooltip("timestamp:T", title="Time"),
            alt.Tooltip("open:Q", title="Open", format=",.2f"),
            alt.Tooltip("high:Q", title="High", format=",.2f"),
            alt.Tooltip("low:Q", title="Low", format=",.2f"),
            alt.Tooltip("close:Q", title="Close", format=",.2f"),
        ],
    )

    bodies = base.mark_bar(size=7).encode(
        y=alt.Y(
            "open:Q",
            scale=alt.Scale(domain=[y_min, y_max], zero=False),
            axis=None,
        ),
        y2="close:Q",
        color=alt.Color("direction:N", scale=color_scale, legend=None),
        tooltip=[
            alt.Tooltip("timestamp:T", title="Time"),
            alt.Tooltip("open:Q", title="Open", format=",.2f"),
            alt.Tooltip("high:Q", title="High", format=",.2f"),
            alt.Tooltip("low:Q", title="Low", format=",.2f"),
            alt.Tooltip("close:Q", title="Close", format=",.2f"),
        ],
    )

    chart = wicks + bodies

    context_zone = zone_dict(get_context_zone(state))
    execution_zone = zone_dict(get_execution_zone(state))
    conflict_zone = zone_dict(get_conflict_zone(state))
    zone_rows = []

    if context_zone and timeframe_label in ("1D", "4H", "1H"):
        zone_rows.append(
            {
                "lower": float(context_zone["lower_bound"]),
                "upper": float(context_zone["upper_bound"]),
                "zone_role": "HTF Context",
            }
        )

    if execution_zone and timeframe_label in ("1H", "30m", "15m", "5m", "1m"):
        zone_rows.append(
            {
                "lower": float(execution_zone["lower_bound"]),
                "upper": float(execution_zone["upper_bound"]),
                "zone_role": "Execution",
            }
        )

    if conflict_zone and timeframe_label in ("1H", "30m", "15m", "5m", "1m"):
        zone_rows.append(
            {
                "lower": float(conflict_zone["lower_bound"]),
                "upper": float(conflict_zone["upper_bound"]),
                "zone_role": "Conflict",
            }
        )

    if zone_rows:
        zone_df = pd.DataFrame(zone_rows)
        zone_layer = (
            alt.Chart(zone_df)
            .mark_rect(opacity=0.105)
            .encode(
                y=alt.Y(
                    "lower:Q",
                    scale=alt.Scale(domain=[y_min, y_max], zero=False),
                    axis=None,
                ),
                y2="upper:Q",
                color=alt.Color(
                    "zone_role:N",
                    scale=alt.Scale(
                        domain=["HTF Context", "Execution", "Conflict"],
                        range=[ACCENT, GREEN, RED],
                    ),
                    legend=alt.Legend(
                        title=None,
                        orient="top",
                        labelColor=MUTED,
                    ),
                ),
                tooltip=[
                    alt.Tooltip("zone_role:N", title="Role"),
                    alt.Tooltip("lower:Q", title="Low", format=",.2f"),
                    alt.Tooltip("upper:Q", title="High", format=",.2f"),
                ],
            )
        )
        chart = chart + zone_layer

    if state.current_price is not None:
        current_df = pd.DataFrame({"price": [state.current_price]})
        current_line = (
            alt.Chart(current_df)
            .mark_rule(
                color=ACCENT_SOFT,
                strokeDash=[5, 4],
                strokeWidth=1.2,
            )
            .encode(
                y=alt.Y(
                    "price:Q",
                    scale=alt.Scale(domain=[y_min, y_max], zero=False),
                    axis=None,
                )
            )
        )
        chart = chart + current_line

    return (
        chart.properties(
            height=560,
            background=PANEL,
            title=f"{DISPLAY_SYMBOL} / {MARKET_NAME} / {timeframe_label}",
        )
        .interactive()
        .configure_view(strokeOpacity=0)
        .configure_axis(
            gridColor="#2a3240",
            gridOpacity=0.20,
            labelFontSize=11,
        )
        .configure_title(
            anchor="start",
            fontSize=14,
            fontWeight=700,
            color="#d9dee7",
            offset=12,
        )
    )


# ---------------------------------------------------------------------
# SETUP / PROFESSOR
# ---------------------------------------------------------------------

def setup_checks(state):
    c = state.confirmation
    return [
        (
            state.market_bias in ("bullish", "bearish"),
            f"Directional bias: {state.market_bias.upper()}",
        ),
        (
            state.selected_zone is not None,
            "Execution zone selected",
        ),
        (
            bool(c.price_in_zone),
            "Price inside execution zone",
        ),
        (
            bool(c.lower_timeframe_confirmed),
            "Lower-timeframe confirmation",
        ),
        (
            bool(c.structural_trigger),
            "Structural trigger",
        ),
        (
            bool(c.risk_validated),
            "Risk validation",
        ),
    ]


def render_setup_validation(state):
    checks = setup_checks(state)
    completed = sum(1 for done, _ in checks if done)

    st.progress(completed / len(checks))
    st.caption(f"{completed}/{len(checks)} deterministic conditions validated")

    for done, label in checks:
        prefix = "[PASS]" if done else "[WAIT]"
        st.markdown(f"**{prefix}** {label}")

    if get_conflict_zone(state):
        st.error("CONFLICT: opposing tactical zone is active.")


def render_watch_plan(state):
    execution = zone_dict(get_execution_zone(state))
    conflict = zone_dict(get_conflict_zone(state))

    direction = state.setup_direction or "NONE"
    if direction == "LONG":
        st.success(f"Directional watch: {direction}")
    elif direction == "SHORT":
        st.error(f"Directional watch: {direction}")
    else:
        st.info("No directional setup currently selected.")

    if execution:
        st.markdown(
            f"**Execution:** {execution.get('timeframe', '--')} "
            f"{str(execution.get('type', '')).upper()} "
            f"{money(execution.get('lower_bound'))} - "
            f"{money(execution.get('upper_bound'))}"
        )
        st.caption(
            f"Distance: {points(execution.get('distance_points'))} "
            f"({safe_float(execution.get('distance_percent'), 0):.3f}%)"
        )

    if conflict:
        st.warning(
            f"Opposing {conflict.get('timeframe', '--')} "
            f"{str(conflict.get('type', '')).upper()} "
            f"{money(conflict.get('lower_bound'))} - "
            f"{money(conflict.get('upper_bound'))}"
        )

    missing = getattr(state.confirmation, "missing_conditions", None) or []
    if missing:
        st.markdown("**Still required**")
        for item in missing:
            st.write(f"- {item}")

    if not state.is_actionable:
        st.info(
            "No validated trade yet. Entry, stop, targets, and probability "
            "remain intentionally blank."
        )


def render_professor_bridge(state):
    status = "READY" if state.professor_ready else "WAITING"
    context = state.professor_context or {}
    architecture_version = context.get("architecture_version", "--")

    st.markdown(
        f"""
        <div class="tp-professor">
            <div class="tp-section-label">SAME BRAIN. SAME MARKETSTATE.</div>
            <div class="tp-prof-title">AI Professor Bridge / {status}</div>
            <div class="tp-prof-copy">
                The Professor receives the exact canonical market snapshot shown
                on this screen. It does not independently invent market conditions,
                trade levels, or probability.
            </div>
            <div class="tp-rule">
                Architecture V{architecture_version} / Symbol {state.root_symbol}
            </div>
            <div class="tp-rule">
                AI-generated trade values:
                {context.get('trade_values_generated_by_ai', False)}
            </div>
            <div class="tp-rule">
                Current setup: {state.setup_state} /
                {state.setup_direction or 'NO DIRECTION'}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.text_input(
        "Ask the Professor about this market",
        placeholder="Example: Why are we watching instead of entering?",
        disabled=True,
        key="professor_question",
    )
    with st.expander("Professor decision packet"):
        st.json(state.professor_payload(), expanded=False)
    st.caption(
        "The conversation layer is next. V2.5 now exposes the exact deterministic "
        "confirmation, risk, and trade-plan state the Professor will explain."
    )


# ---------------------------------------------------------------------
# SESSION / MARKETSTATE
# ---------------------------------------------------------------------

if "chart_tf" not in st.session_state:
    st.session_state.chart_tf = DEFAULT_CHART_TF

with st.spinner("Building canonical GC MarketState..."):
    try:
        market_state = get_market_state()
    except Exception as exc:
        st.error(f"Unable to build MarketState: {exc}")
        st.stop()

health, age_minutes = data_health(market_state.market_timestamp)
news_warning, news_level = get_news_state()


# ---------------------------------------------------------------------
# HEADER
# ---------------------------------------------------------------------

st.markdown('<div class="tp-topline"></div>', unsafe_allow_html=True)

header_left, header_right = st.columns([5.2, 2.2], gap="large")

with header_left:
    logo_col, copy_col = st.columns([1.7, 3.8], gap="medium")
    with logo_col:
        st.image("assets/ttp_logo.webp", use_container_width=True)
    with copy_col:
        st.markdown(
            f"""
            <div class="tp-hero">
                <div class="tp-hero-tag">AI ASSISTED FUTURES TRADING</div>
                <div class="tp-title">{COACH_NAME}</div>
                <div class="tp-hero-copy">
                    Stop Chasing Trades. Let the Market Come to You.<br>
                    <span style="color:#b3bdcb">
                    {DISPLAY_SYMBOL} / {MARKET_NAME} / FRONT-MONTH ARCHITECTURE /
                    DATA: {get_data_source_name()}
                    </span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

with header_right:
    h1, h2 = st.columns(2)
    h1.metric("GC PRICE", money(market_state.current_price))
    h2.metric("DATA FEED", health)

if market_state.market_timestamp:
    try:
        local_ts = pd.Timestamp(market_state.market_timestamp)
        if local_ts.tzinfo is None:
            local_ts = local_ts.tz_localize("UTC")
        local_ts = local_ts.tz_convert("America/Los_Angeles")
        st.caption(
            "MarketState candle: "
            f"{local_ts.strftime('%Y-%m-%d %H:%M:%S %Z')} / "
            "Yahoo futures data may be delayed."
        )
    except Exception:
        st.caption(f"MarketState timestamp: {market_state.market_timestamp}")


# ---------------------------------------------------------------------
# CONTROL STRIP
# ---------------------------------------------------------------------

control_left, control_mid, control_right = st.columns([1.2, 4.8, 1.25], gap="medium")

with control_left:
    if st.button("REFRESH MARKET", use_container_width=True, type="primary"):
        with st.spinner("Refreshing Gold futures data..."):
            success = fetch_latest_data()
        st.cache_data.clear()
        st.cache_resource.clear()
        if not success:
            st.error("Market-data refresh failed.")
        st.rerun()

with control_mid:
    if news_level == "HIGH":
        st.error(f"HIGH EVENT RISK: {news_warning}")
    elif news_level == "MEDIUM":
        st.warning(f"EVENT RISK: {news_warning}")
    elif news_level == "UNKNOWN":
        st.info("Economic-event status unavailable.")
    else:
        st.success("No major event warning from the current news engine.")

with control_right:
    age_text = "--" if age_minutes is None else f"{age_minutes:.0f}m"
    st.caption(
        f"DATA AGE {age_text}\n\n"
        f"UI {datetime.now().strftime('%H:%M:%S')}"
    )


# ---------------------------------------------------------------------
# COMMAND CENTER
# ---------------------------------------------------------------------

st.divider()
render_section("LIVE DECISION ENGINE", "Market Command Center")

m1, m2, m3, m4, m5 = st.columns(5)

m1.metric("MARKET BIAS", market_state.market_bias.upper())
m2.metric("ALIGNMENT", f"{market_state.alignment_score:.1f}%")
m3.metric("SETUP STATE", market_state.setup_state)
m4.metric("DIRECTION", market_state.setup_direction or "--")
m5.metric("TRADE READY", "YES" if market_state.is_actionable else "NO")

st.caption(
    "Alignment is weighted directional agreement across timeframes. "
    "It is not win probability."
)


# ---------------------------------------------------------------------
# TABS
# ---------------------------------------------------------------------

dashboard_tab, journal_tab, stats_tab, backtest_tab, system_tab = st.tabs(
    [
        "COMMAND CENTER",
        "JOURNAL",
        "PERFORMANCE",
        "BACKTEST",
        "SYSTEM",
    ]
)


# ---------------------------------------------------------------------
# COMMAND CENTER TAB
# ---------------------------------------------------------------------

with dashboard_tab:
    st.write("")
    render_section("PRICE ACTION", "Live Market")

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

    chart_col, side_col = st.columns([3.45, 1.15], gap="large")

    with chart_col:
        selected_tf = st.session_state.chart_tf
        try:
            chart_df = get_chart_data(selected_tf, 260)
            if chart_df is not None and len(chart_df) >= 5:
                chart = build_candlestick_chart(
                    chart_df,
                    selected_tf,
                    market_state,
                )
                if chart is not None:
                    st.altair_chart(chart, use_container_width=True)

                last_candle = chart_df.iloc[-1]
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("OPEN", money(last_candle["open"]))
                c2.metric("HIGH", money(last_candle["high"]))
                c3.metric("LOW", money(last_candle["low"]))
                c4.metric("CLOSE", money(last_candle["close"]))

                note = (
                    f"{len(chart_df):,} candles / "
                    "only decision-useful MarketState zones are overlaid"
                )
                if selected_tf == "30m":
                    note += " / 30m currently resampled from 15m"
                st.caption(note)
            else:
                st.warning(f"Not enough {selected_tf} data.")
        except Exception as exc:
            st.error(f"Chart error: {exc}")

    with side_col:
        render_section("NOW", "MarketState")

        state_variant = "gold"
        if market_state.is_actionable:
            state_variant = "green"
        elif get_conflict_zone(market_state):
            state_variant = "red"

        st.markdown(
            f"""
            <div class="tp-card {state_variant}">
                <div class="tp-kicker">SETUP STATUS</div>
                <div class="tp-value gold">{market_state.setup_state}</div>
                <div class="tp-detail">
                    Bias {market_state.market_bias.upper()}<br>
                    Alignment {market_state.alignment_score:.1f}%<br>
                    Direction {market_state.setup_direction or 'NONE'}<br>
                    Trade ready {'YES' if market_state.is_actionable else 'NO'}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.write("")
        render_zone_card(
            "EXECUTION ZONE",
            get_execution_zone(market_state),
            "Execution",
            "gold",
        )

        if get_conflict_zone(market_state):
            st.write("")
            render_zone_card(
                "ACTIVE CONFLICT",
                get_conflict_zone(market_state),
                "Conflict",
                "red",
            )

        st.write("")
        st.metric("HISTORICAL WIN PROBABILITY", "--")
        st.caption(
            "Not fabricated. Requires comparable historical setups and "
            "a valid sample size."
        )

    st.divider()
    render_section("LOCATION MATTERS", "Decision Zones")

    z1, z2, z3 = st.columns(3, gap="large")
    with z1:
        render_zone_card(
            "HIGHER-TIMEFRAME CONTEXT",
            get_context_zone(market_state),
            "Context",
        )
    with z2:
        render_zone_card(
            "TACTICAL EXECUTION",
            get_execution_zone(market_state),
            "Execution",
            "gold",
        )
    with z3:
        render_zone_card(
            "OPPOSING CONFLICT",
            get_conflict_zone(market_state),
            "Conflict",
            "red" if get_conflict_zone(market_state) else "",
        )

    st.divider()
    render_section("TOP DOWN", "Multi-Timeframe Alignment")

    trend_cols = st.columns(len(TREND_DISPLAY_ORDER))
    for index, (label, key) in enumerate(TREND_DISPLAY_ORDER):
        trend = market_state.trends.get(key, "no_data")
        css_trend = trend if trend in ("bullish", "bearish", "neutral") else "neutral"
        if trend == "bullish":
            display_trend = "BULLISH"
        elif trend == "bearish":
            display_trend = "BEARISH"
        elif trend == "neutral":
            display_trend = "NEUTRAL"
        else:
            display_trend = "NO DATA"

        trend_cols[index].markdown(
            f"""
            <div class="tp-trend-card {css_trend}">
                <div class="tp-trend-tf">{label}</div>
                <div class="tp-trend-value {css_trend}">{display_trend}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.caption(
        "Monthly through 1-minute context feeds the canonical MarketState. "
        "Higher timeframes define context; lower timeframes refine execution."
    )

    st.divider()
    render_section("NO GUESSING", "Setup Validation")

    checklist_col, plan_col = st.columns([1.05, 1], gap="large")

    with checklist_col:
        render_setup_validation(market_state)

    with plan_col:
        render_watch_plan(market_state)

    if market_state.trade is not None:
        st.divider()
        render_section("DETERMINISTIC EXECUTION", "Qualified Trade Plan")
        trade = market_state.trade
        t1, t2, t3, t4 = st.columns(4)
        t1.metric("ENTRY", money(trade.entry))
        t2.metric("STOP", money(trade.stop))
        t3.metric("RISK / CONTRACT", money(trade.risk_dollars_per_contract))
        t4.metric("SETUP GRADE", trade.setup_grade or "--")

        if trade.targets:
            target_cols = st.columns(len(trade.targets))
            for idx, target in enumerate(trade.targets):
                target_cols[idx].metric(
                    target.name,
                    money(target.price),
                    f"{target.rr_ratio:.1f}R",
                )
        st.caption(
            "Rule-generated only after all V2.5 confirmation and risk checks pass. "
            "Historical win probability remains blank until statistically validated."
        )

    st.divider()
    render_section("THE PROFESSOR", "Market Intelligence Interface")

    professor_col, engine_col = st.columns([1.35, 1], gap="large")

    with professor_col:
        render_professor_bridge(market_state)

    with engine_col:
        completed_stack = [
            "Canonical MarketState",
            "Monthly through 1m trend context",
            "HTF context-zone hierarchy",
            "Tactical execution zones",
            "Zone-width penalty",
            "Opposing-zone conflict detection",
            "Setup lifecycle",
            "Professor context bridge",
        ]
        next_stack = [
            "Professor conversation layer",
            "Comparable-setup probability",
            "Multi-symbol storage migration",
            "Multi-symbol futures scanner",
            "Cross-market opportunity ranking",
        ]

        st.markdown("**ACTIVE INTELLIGENCE**")
        for item in completed_stack:
            st.write(f"[LIVE] {item}")

        st.markdown("**NEXT LAYERS**")
        for item in next_stack:
            st.write(f"[NEXT] {item}")


# ---------------------------------------------------------------------
# JOURNAL TAB
# ---------------------------------------------------------------------

with journal_tab:
    st.write("")
    render_section("TRADE MEMORY", "Journal")

    st.caption(
        "Existing journal preserved while deterministic V2 execution logic "
        "continues to be developed."
    )

    try:
        trades_df = get_all_trades()

        if len(trades_df) > 0:
            for _, trade_row in trades_df.head(30).iterrows():
                outcome = str(trade_row["outcome"])
                title = (
                    f"#{trade_row['id']} / {trade_row['direction']} "
                    f"@ {money(trade_row['entry'])} / "
                    f"Grade {trade_row['grade']} / {outcome}"
                )

                with st.expander(title):
                    c1, c2 = st.columns(2)

                    with c1:
                        st.write(f"Entry: {money(trade_row['entry'])}")
                        st.write(f"Stop: {money(trade_row['stop'])}")
                        st.write(f"Target: {money(trade_row['target'])}")

                    with c2:
                        st.write(f"Outcome: {outcome}")

                        exit_value = trade_row["exit_price"]
                        if exit_value is not None and str(exit_value) != "nan":
                            st.write(f"Exit: {money(exit_value)}")

                        pnl_value = trade_row["pnl"]
                        if pnl_value is not None and str(pnl_value) != "nan":
                            st.write(f"P&L: {money(pnl_value)}")

                    if outcome == "OPEN":
                        new_outcome = st.selectbox(
                            "Update Outcome",
                            ["OPEN", "WIN", "LOSS", "BREAKEVEN"],
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
            st.info("No trades in journal.")

    except Exception as exc:
        st.error(f"Journal error: {exc}")


# ---------------------------------------------------------------------
# PERFORMANCE TAB
# ---------------------------------------------------------------------

with stats_tab:
    st.write("")
    render_section("EDGE TRACKING", "Performance")

    try:
        stats = calculate_statistics()

        if stats:
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("TRADES", stats["total_trades"])
            c2.metric("WIN RATE", f"{stats['win_rate']}%")
            c3.metric("PROFIT FACTOR", stats["profit_factor"])
            c4.metric("EXPECTANCY", money(stats["expectancy"]))
            c5.metric("TOTAL P&L", money(stats["total_pnl"]))

            st.divider()

            try:
                dna_df = analyze_dna_performance()
                if len(dna_df) > 0:
                    render_section("PATTERN MEMORY", "Trade DNA")
                    st.dataframe(dna_df, use_container_width=True)
            except Exception:
                pass
        else:
            st.info("No closed trades yet.")

    except Exception as exc:
        st.error(f"Statistics error: {exc}")


# ---------------------------------------------------------------------
# BACKTEST TAB
# ---------------------------------------------------------------------

with backtest_tab:
    st.write("")
    render_section("HISTORICAL LAB", "Backtest")

    st.warning(
        "This remains the legacy V1 backtester. Its results are NOT the "
        "V2 MarketState comparable-setup probability engine."
    )

    try:
        available_years = get_available_years()

        if available_years:
            st.caption(
                f"Historical data: {available_years[0]} through "
                f"{available_years[-1]}"
            )

            col1, col2, col3 = st.columns(3)

            with col1:
                selected_year = st.selectbox(
                    "Year",
                    ["All"] + [str(y) for y in available_years],
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
                )

            with col3:
                use_trailing_stop = st.checkbox(
                    "Use Trailing Stop",
                    value=False,
                )

            if st.button(
                "RUN LEGACY BACKTEST",
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

                if result and result["stats"]["total_trades"] > 0:
                    rs = result["stats"]
                    r1, r2, r3, r4 = st.columns(4)
                    r1.metric("TRADES", rs["total_trades"])
                    r2.metric("WIN RATE", f"{rs['win_rate']:.1f}%")
                    r3.metric("PROFIT FACTOR", f"{rs['profit_factor']:.2f}")
                    r4.metric("RETURN", f"{rs['total_return']:.1f}%")
                else:
                    st.warning("No trades generated.")
        else:
            st.warning("No historical data.")

    except Exception as exc:
        st.error(f"Backtest error: {exc}")


# ---------------------------------------------------------------------
# SYSTEM TAB
# ---------------------------------------------------------------------

with system_tab:
    st.write("")
    render_section("UNDER THE HOOD", "System / MarketState Diagnostics")

    sys1, sys2, sys3, sys4 = st.columns(4)

    sys1.metric("DASHBOARD", "V2.5.1")
    sys2.metric(
        "MARKETSTATE",
        market_state.engine_versions.get("market_state", "--"),
    )
    sys3.metric("SYMBOL", market_state.root_symbol)
    sys4.metric(
        "PROFESSOR READY",
        "YES" if market_state.professor_ready else "NO",
    )

    st.divider()
    render_section("VERSIONS", "Engine Stack")

    if market_state.engine_versions:
        versions_df = pd.DataFrame(
            [
                {"Engine": key, "Version": value}
                for key, value in market_state.engine_versions.items()
            ]
        )
        st.dataframe(
            versions_df,
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    render_section("DATA", "Database Inventory")

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                timeframe,
                COUNT(*),
                MIN(timestamp),
                MAX(timestamp)
            FROM gold_ohlcv
            GROUP BY timeframe
            ORDER BY timeframe
            """
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if rows:
            db_df = pd.DataFrame(
                rows,
                columns=[
                    "Timeframe",
                    "Candles",
                    "Oldest",
                    "Newest",
                ],
            )
            st.dataframe(
                db_df,
                use_container_width=True,
                hide_index=True,
            )
    except Exception as exc:
        st.error(f"Database diagnostics error: {exc}")

    st.divider()
    render_section("GUARDRAILS", "MarketState Warnings")

    if market_state.warnings:
        for warning in market_state.warnings:
            st.warning(warning)
    else:
        st.success("No MarketState warnings.")

    st.divider()
    render_section("AI BRIDGE", "Professor Context Payload")
    st.json(market_state.professor_context, expanded=False)

    st.divider()
    render_section("EVENTS", "Economic Event Output")

    try:
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        display_news_calendar()
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        if output.strip():
            st.text(output)
        else:
            st.caption("No event-calendar text returned.")

    except Exception as exc:
        try:
            sys.stdout = old_stdout
        except Exception:
            pass
        st.caption(f"News calendar unavailable: {exc}")

    st.divider()
    render_section("BUILD PATH", "Architecture Roadmap")

    roadmap = pd.DataFrame(
        [
            ["V2.2", "Canonical MarketState", "COMPLETE"],
            ["V2.4", "Trading Pulse Command Center", "COMPLETE"],
            ["V2.5", "Confirmation + Risk + Trade Plan", "CURRENT"],
            ["V2.6", "Professor Conversation", "NEXT"],
            ["V2.7", "Comparable Setup Backtesting", "PLANNED"],
            ["V2.8", "AI Professor Conversation", "PLANNED"],
            ["V2.9", "Multi-Symbol Futures Scanner", "PLANNED"],
            ["V3.0", "Cross-Market Opportunity Ranking", "PLANNED"],
        ],
        columns=["Milestone", "Scope", "Status"],
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
st.markdown(
    """
    <div class="tp-footer">
        THE TRADING PULSE / GOLD TRADING COACH V2.5.1 /
        CANONICAL MARKETSTATE ARCHITECTURE /
        EDUCATIONAL MARKET-ANALYSIS SOFTWARE / NOT FINANCIAL ADVICE
    </div>
    """,
    unsafe_allow_html=True,
)
