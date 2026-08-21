"""
THE TRADING PULSE
Gold Trading Coach V2.9C Dashboard

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
from pathlib import Path
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
from setup_candidate_engine import build_setup_candidates, filter_candidates, GRADE_RANK
from execution_lifecycle_engine import build_execution_lifecycle, candidate_stage, broker_order_intent
from live_data_engine import fetch_latest_data, get_data_source_name
from journal_engine import calculate_statistics, get_all_trades, update_outcome
from dna_engine import analyze_dna_performance
from news_engine import generate_news_warning, display_news_calendar
from backtest_engine import run_backtest, get_available_years
from market_watch_engine import fetch_market_watch


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
PROJECT_ROOT = Path(__file__).resolve().parent
BRAND_LOGO = PROJECT_ROOT / "assets" / "TTP_Text.JPG"

MARKET_WATCH_ORDER = ["GC", "SI", "ES", "NQ", "YM", "RTY", "CL", "NG"]
MARKET_WATCH_META = {
    "GC":  ("Gold", "GC=F"),
    "SI":  ("Silver", "SI=F"),
    "ES":  ("S&P 500", "ES=F"),
    "NQ":  ("Nasdaq 100", "NQ=F"),
    "YM":  ("Dow", "YM=F"),
    "RTY": ("Russell 2000", "RTY=F"),
    "CL":  ("Crude Oil", "CL=F"),
    "NG":  ("Natural Gas", "NG=F"),
}


# ---------------------------------------------------------------------
# BRAND CSS
# ---------------------------------------------------------------------

st.markdown(
    f"""
    <style>
    .tp-brand-logo img {{
        width: 100%;
        max-width: 310px;
        object-fit: contain;
    }}
    .tp-coach-name {{
        color: #e0b85b;
        font-size: 1.22rem;
        font-weight: 900;
        letter-spacing: .035em;
        line-height: 1.05;
        padding-top: 3px;
    }}
    .tp-coach-sub {{
        color: #9da8b7;
        font-size: .72rem;
        letter-spacing: .045em;
        margin-top: 5px;
    }}
    .tp-live-market-row {{
        margin-top: 10px;
        margin-bottom: 3px;
    }}

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


    /* ================================================================
       COMMAND CENTER V2.8H - FINAL PRE-2.9 CLEANUP
       ================================================================ */
    .block-container {{ max-width: 1900px; padding-left: 1.45rem; padding-right: 1.45rem; }}
    .tp-topline, .tp-hero, .tp-brand-row {{ }}
    .tp-command-title {{ margin: 2px 0 10px 0; }}
    .tp-command-kicker {{ color:#d7b45a; font-size:.66rem; font-weight:850; letter-spacing:.16em; }}
    .tp-command-name {{ color:#f5f7fa; font-size:1.08rem; font-weight:850; margin-top:4px; }}
    .tp-status-grid {{
        display:grid; grid-template-columns: repeat(5,minmax(0,1fr));
        border:1px solid #36404e; border-radius:9px; overflow:hidden;
        background:linear-gradient(145deg,#10161f,#0a0f16); margin:12px 0 12px 0;
    }}
    .tp-status-cell {{ min-height:116px; padding:18px 18px 14px; border-right:1px solid #2b3440; }}
    .tp-status-cell:last-child {{ border-right:none; }}
    .tp-status-label {{ color:#d5dae3; font-size:.72rem; font-weight:800; letter-spacing:.04em; }}
    .tp-status-value {{ font-size:1.34rem; font-weight:900; margin-top:13px; letter-spacing:.01em; }}
    .tp-status-sub {{ color:#aab4c2; font-size:.72rem; margin-top:12px; }}
    .tp-bull {{ color:#35c76f; }} .tp-bear {{ color:#ff4d57; }}
    .tp-watch {{ color:#e4b94f; }} .tp-no {{ color:#ff4d57; }} .tp-yes {{ color:#35c76f; }}
    .tp-dash {{ color:#8993a1; }}
    .tp-panelbox {{
        border:1px solid #36404e; border-radius:9px;
        background:linear-gradient(145deg,#10161f,#0a0f16); padding:15px 16px;
    }}
    .tp-mtf-head {{ color:#aeb8c6; font-size:.72rem; letter-spacing:.08em; font-weight:800; }}
    .tp-mtf-big {{ color:#35c76f; font-size:1.55rem; font-weight:900; margin-top:9px; }}
    .tp-mtf-sub {{ color:#c6ccd5; font-size:.73rem; margin-top:3px; }}
    .tp-mini-bars {{ height:40px; display:flex; align-items:flex-end; gap:9px; margin-top:7px; }}
    .tp-mini-bars span {{ width:16px; background:#1f6d42; border-radius:1px 1px 0 0; }}
    .tp-mini-labels {{ display:flex; justify-content:space-between; color:#8993a1; font-size:.58rem; margin-top:4px; }}
    .tp-intel-card {{
        border:1px solid #36404e; border-radius:8px; background:#0d131b;
        padding:16px; margin-bottom:12px; min-height:105px;
    }}
    .tp-intel-title {{ font-size:.68rem; font-weight:850; letter-spacing:.08em; color:#aeb8c6; }}
    .tp-intel-title.green {{ color:#35c76f; }} .tp-intel-title.red {{ color:#ff4d57; }}
    .tp-intel-value {{ color:#f4f6f9; font-size:1.08rem; font-weight:900; margin-top:10px; }}
    .tp-intel-detail {{ color:#aeb8c6; font-size:.67rem; line-height:1.55; margin-top:7px; }}
    .tp-chart-head {{
        border:1px solid #36404e; border-bottom:none; border-radius:8px 8px 0 0;
        padding:13px 16px; background:#0d131b; color:#eef1f5; font-size:.82rem; font-weight:800;
    }}
    .tp-footnote {{ color:#7f8997; font-size:.66rem; margin-top:8px; }}
    .tp-feed-dot {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:7px; }}
    .tp-feed-dot.green {{ background:#35c76f; box-shadow:0 0 10px rgba(53,199,111,.35); }}
    .tp-feed-dot.red {{ background:#ff4d57; box-shadow:0 0 10px rgba(255,77,87,.35); }}
    .tp-feed-wrap {{ text-align:right; color:#9fa9b7; font-size:.68rem; padding-top:5px; }}
    div[data-testid="stMetric"] {{
        background:linear-gradient(145deg,#10161f,#0a0f16);
        border:1px solid #36404e; border-radius:8px; padding:12px 14px;
    }}
    div[data-testid="stMetric"] label {{ color:#b8c0cc !important; font-size:.67rem !important; }}
    div[data-testid="stMetricValue"] {{ font-size:1.55rem !important; }}
    div.stButton > button {{
        min-height:38px; border-radius:7px; border-color:#34404f;
        background:#0e141d; color:#dce2ea;
    }}
    div.stButton > button[kind="primary"] {{
        color:#11151b; font-weight:850;
        background:linear-gradient(180deg,#e0b85b,#bd8d37); border-color:#e2bd63;
    }}
    div[data-testid="stExpander"] {{ border-color:#36404e !important; background:#0d131b !important; }}
    div[data-testid="stCheckbox"] label p {{ color:#c8ced7 !important; font-size:.76rem !important; }}

    .tp-market-watch-wrap {{
        margin: 10px 0 14px 0;
        padding: 10px 12px 12px;
        border: 1px solid #242c39;
        border-radius: 10px;
        background: linear-gradient(180deg, rgba(17,23,34,.96), rgba(10,14,20,.96));
    }}
    .tp-market-watch-head {{
        display:flex;
        align-items:baseline;
        justify-content:space-between;
        margin-bottom:8px;
    }}
    .tp-market-watch-title {{
        color:#f5f7fa;
        font-size:.72rem;
        font-weight:900;
        letter-spacing:.12em;
    }}
    .tp-market-watch-sub {{
        color:#7f8a99;
        font-size:.64rem;
    }}
    .tp-market-grid {{
        display:grid;
        grid-template-columns:repeat(8,minmax(0,1fr));
        gap:7px;
    }}
    .tp-market-card {{
        min-width:0;
        border:1px solid #28313d;
        border-radius:8px;
        padding:9px 9px 8px;
        background:#0b1017;
        box-shadow:inset 0 1px 0 rgba(255,255,255,.02);
    }}
    .tp-market-card.active {{
        border-color:rgba(215,180,90,.72);
        box-shadow:0 0 0 1px rgba(215,180,90,.12), inset 0 1px 0 rgba(255,255,255,.03);
    }}
    .tp-market-top {{
        display:flex;
        justify-content:space-between;
        align-items:center;
        gap:5px;
    }}
    .tp-market-symbol {{
        color:#f7f8fb;
        font-weight:900;
        font-size:.76rem;
        letter-spacing:.04em;
    }}
    .tp-market-dot {{
        width:6px;height:6px;border-radius:50%;display:inline-block;background:#667085;
    }}
    .tp-market-dot.up {{ background:#22c55e; box-shadow:0 0 7px rgba(34,197,94,.35); }}
    .tp-market-dot.down {{ background:#ef4444; box-shadow:0 0 7px rgba(239,68,68,.35); }}
    .tp-market-name {{
        color:#7f8a99;
        font-size:.58rem;
        white-space:nowrap;
        overflow:hidden;
        text-overflow:ellipsis;
        margin-top:1px;
    }}
    .tp-market-price {{
        color:#f5f7fa;
        font-weight:850;
        font-size:.86rem;
        margin-top:6px;
        white-space:nowrap;
    }}
    .tp-market-change {{
        font-size:.60rem;
        margin-top:2px;
        white-space:nowrap;
    }}
    .tp-market-change.up {{ color:#22c55e; }}
    .tp-market-change.down {{ color:#ef4444; }}
    .tp-market-change.flat {{ color:#a7b0bd; }}
    .tp-market-spark {{
        width:100%;
        height:15px;
        margin-top:5px;
        opacity:.92;
    }}
    .tp-market-note {{
        color:#6f7a89;
        font-size:.56rem;
        margin-top:7px;
    }}
    @media (max-width: 1450px) {{
        .tp-market-grid {{ grid-template-columns:repeat(4,minmax(0,1fr)); }}
    }}
    @media (max-width: 850px) {{
        .tp-market-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
    }}

    @media (max-width: 1100px) {{
        .tp-status-grid {{ grid-template-columns:1fr 1fr; }}
        .tp-status-cell {{ border-bottom:1px solid #2b3440; }}
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


@st.cache_data(ttl=45, show_spinner=False)
def get_market_watch():
    return fetch_market_watch(MARKET_WATCH_ORDER)


def _sparkline_svg(values, positive=True):
    values = [safe_float(v) for v in (values or [])]
    values = [v for v in values if v is not None]
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    span = max(hi - lo, 1e-9)
    pts = []
    for i, value in enumerate(values[-24:]):
        x = i / max(len(values[-24:]) - 1, 1) * 100
        y = 13 - ((value - lo) / span * 11)
        pts.append(f"{x:.1f},{y:.1f}")
    stroke = "#22c55e" if positive else "#ef4444"
    return (
        '<svg class="tp-market-spark" viewBox="0 0 100 15" preserveAspectRatio="none">'
        f'<polyline points="{" ".join(pts)}" fill="none" stroke="{stroke}" '
        'stroke-width="1.4" vector-effect="non-scaling-stroke"/></svg>'
    )


def render_market_watch(cards):
    cards = cards or {}
    html = [
        '<div class="tp-market-watch-wrap">',
        '<div class="tp-market-watch-head">',
        '<div class="tp-market-watch-title">MARKET WATCH</div>',
        '<div class="tp-market-watch-sub">Yahoo Finance futures snapshot / GC Command Center active</div>',
        '</div>',
        '<div class="tp-market-grid">',
    ]
    for symbol in MARKET_WATCH_ORDER:
        meta_name, _ = MARKET_WATCH_META[symbol]
        item = cards.get(symbol, {})
        price = safe_float(item.get("price"))
        change = safe_float(item.get("change"), 0.0)
        pct = safe_float(item.get("change_pct"), 0.0)
        direction = "up" if change > 0 else "down" if change < 0 else "flat"
        active = " active" if symbol == "GC" else ""
        dot_cls = "up" if change > 0 else "down" if change < 0 else ""
        price_text = "--" if price is None else f"{price:,.2f}"
        change_text = "--" if price is None else f"{change:+,.2f}  ({pct:+.2f}%)"
        spark = _sparkline_svg(item.get("sparkline"), positive=change >= 0)
        html.extend([
            f'<div class="tp-market-card{active}" title="{symbol} / {meta_name}">',
            '<div class="tp-market-top">',
            f'<div class="tp-market-symbol">{symbol}</div>',
            f'<span class="tp-market-dot {dot_cls}"></span>',
            '</div>',
            f'<div class="tp-market-name">{meta_name}</div>',
            f'<div class="tp-market-price">{price_text}</div>',
            f'<div class="tp-market-change {direction}">{change_text}</div>',
            spark,
            '</div>',
        ])
    html.extend([
        '</div>',
        '<div class="tp-market-note">GC has full Trading Pulse analysis. The other seven are watch-feed only until their deterministic engines and storage are validated.</div>',
        '</div>',
    ])
    st.markdown("".join(html), unsafe_allow_html=True)


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



def candidate_for_zone(state, zone):
    z = zone_dict(zone) or {}
    for candidate in build_setup_candidates(state):
        if (
            candidate.zone_type == str(z.get("type", "")).lower()
            and candidate.timeframe == str(z.get("timeframe", ""))
            and abs(candidate.lower_bound - safe_float(z.get("lower_bound"), 0.0)) < 0.001
            and abs(candidate.upper_bound - safe_float(z.get("upper_bound"), 0.0)) < 0.001
        ):
            return candidate
    return None


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

def build_candlestick_chart(
    df,
    timeframe_label,
    state,
    min_zone_grade="ALL",
    show_context=True,
    show_execution=True,
    show_conflict=True,
    show_sma20=False,
    show_sma50=False,
    show_sma200=False,
    show_ema9=False,
    show_ema21=False,
    show_vwap=False,
    show_prev_day=False,
    show_prev_week=False,
    show_volume=False,
    show_grade_aplus=True,
    show_grade_a=True,
    show_grade_b=True,
    show_grade_c=False,
):
    if df is None or len(df) < 2:
        return None

    data = df.copy().tail(260).reset_index()
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
    y_min = price_min - price_range * 0.05
    y_max = price_max + price_range * 0.05

    x_enc = alt.X("timestamp:T", axis=alt.Axis(
        title=None, format="%b %d", labelAngle=0, labelOverlap=True,
        labelColor=MUTED, tickColor=BORDER, domainColor=BORDER))
    y_enc = alt.Y("low:Q", scale=alt.Scale(domain=[y_min, y_max], zero=False),
        axis=alt.Axis(title=None, orient="right", labelColor=MUTED,
                      tickColor=BORDER, domainColor=BORDER, format=",.2f"))
    colors = alt.Scale(domain=["Up", "Down"], range=[GREEN, RED])
    base = alt.Chart(data).encode(x=x_enc)
    wicks = base.mark_rule(strokeWidth=1.0).encode(
        y=y_enc, y2="high:Q", color=alt.Color("direction:N", scale=colors, legend=None))
    bodies = base.mark_bar(size=6).encode(
        y=alt.Y("open:Q", scale=alt.Scale(domain=[y_min, y_max], zero=False), axis=None),
        y2="close:Q", color=alt.Color("direction:N", scale=colors, legend=None),
        tooltip=[alt.Tooltip("timestamp:T", title="Time"),
                 alt.Tooltip("open:Q", title="Open", format=",.2f"),
                 alt.Tooltip("high:Q", title="High", format=",.2f"),
                 alt.Tooltip("low:Q", title="Low", format=",.2f"),
                 alt.Tooltip("close:Q", title="Close", format=",.2f")])
    chart = wicks + bodies

    # V2.9B: chart grades are SETUP grades from the canonical Setup Candidate Engine.
    # One grading brain now drives BOTH the chart and candidate intelligence.
    grade_switches = {
        "A+": show_grade_aplus,
        "A": show_grade_a,
        "B": show_grade_b,
        "C": show_grade_c,
        "D": False,
    }

    def allowed_market_state(zone):
        return bool(zone_dict(zone))

    zone_rows = []
    context_zone = get_context_zone(state)
    execution_zone = get_execution_zone(state)
    conflict_zone = get_conflict_zone(state)

    tf_map = {"1D": "D", "1W": "W"}
    active_tf = tf_map.get(timeframe_label, timeframe_label)
    if active_tf in ("1m", "5m", "15m", "30m", "1H"):
        relevant_tfs = {active_tf, "1H", "4H", "D"}
    elif active_tf == "4H":
        relevant_tfs = {"4H", "D"}
    elif active_tf in ("D", "W"):
        relevant_tfs = {"D"}
    else:
        relevant_tfs = {active_tf}

    all_candidates = build_setup_candidates(state)
    visible_candidates = filter_candidates(
        all_candidates,
        minimum_grade=min_zone_grade,
        enabled_grades=grade_switches,
        relevant_timeframes=relevant_tfs,
        limit=6,
    )

    for candidate in visible_candidates:
        zone_rows.append({
            "lower": candidate.lower_bound,
            "upper": candidate.upper_bound,
            "zone_role": "Potential Demand" if candidate.zone_type == "demand" else "Potential Supply",
            "grade": candidate.grade,
            "zone_grade": candidate.zone_grade,
            "setup_score": candidate.setup_score,
            "distance": candidate.distance_percent,
            "timeframe": candidate.timeframe,
            "candidate_label": f"{candidate.grade} SETUP / {candidate.zone_grade} ZONE / {candidate.timeframe} {candidate.zone_type.upper()} / {candidate.lifecycle}",
        })

    # Canonical MarketState overlays remain separate and OFF by default.
    if show_context and allowed_market_state(context_zone):
        z = zone_dict(context_zone)
        zone_rows.append({"lower":float(z["lower_bound"]), "upper":float(z["upper_bound"]),
                          "zone_role":"HTF Context", "grade":str(z.get("grade","--"))})
    if show_execution and allowed_market_state(execution_zone):
        z = zone_dict(execution_zone)
        zone_rows.append({"lower":float(z["lower_bound"]), "upper":float(z["upper_bound"]),
                          "zone_role":"Execution", "grade":str(z.get("grade","--"))})
    if show_conflict and allowed_market_state(conflict_zone):
        z = zone_dict(conflict_zone)
        zone_rows.append({"lower":float(z["lower_bound"]), "upper":float(z["upper_bound"]),
                          "zone_role":"Conflict", "grade":str(z.get("grade","--"))})

    if zone_rows:
        # Keep the chart decision-useful: collapse duplicate / near-identical bands.
        cleaned = []
        for row in zone_rows:
            duplicate = False
            for kept in cleaned:
                same_role = row["zone_role"] == kept["zone_role"]
                overlap = min(row["upper"], kept["upper"]) - max(row["lower"], kept["lower"])
                min_width = max(min(row["upper"] - row["lower"], kept["upper"] - kept["lower"]), 0.01)
                if same_role and overlap > 0 and (overlap / min_width) >= 0.60:
                    duplicate = True
                    break
            if not duplicate:
                cleaned.append(row)
        zone_rows = cleaned[:6]

        zdf = pd.DataFrame(zone_rows)
        zone_layer = alt.Chart(zdf).mark_rect(opacity=.10).encode(
            y=alt.Y("lower:Q", scale=alt.Scale(domain=[y_min,y_max], zero=False), axis=None),
            y2="upper:Q",
            color=alt.Color("zone_role:N",
                scale=alt.Scale(
                    domain=["Potential Demand","Potential Supply","HTF Context","Execution","Conflict"],
                    range=["#2f9e5b","#c94b52",ACCENT,GREEN,RED]
                ), legend=None),
            tooltip=[alt.Tooltip("zone_role:N",title="Zone"),
                     alt.Tooltip("grade:N",title="Setup Grade"),
                     alt.Tooltip("zone_grade:N",title="Zone Grade"),
                     alt.Tooltip("lower:Q",title="Low",format=",.2f"),
                     alt.Tooltip("upper:Q",title="High",format=",.2f")])
        chart = zone_layer + chart

        # Label potential zones with the SAME V2.9A grade/lifecycle used by the filter.
        label_rows = [r for r in zone_rows if r.get("candidate_label")]
        if label_rows:
            last_ts = data["timestamp"].max()
            ldf = pd.DataFrame([{
                "timestamp": last_ts,
                "price": (r["lower"] + r["upper"]) / 2.0,
                "label": r["candidate_label"],
            } for r in label_rows])
            labels = alt.Chart(ldf).mark_text(
                align="right", dx=-6, fontSize=10, fontWeight="bold", color=TEXT
            ).encode(
                x=alt.X("timestamp:T", axis=None),
                y=alt.Y("price:Q", scale=alt.Scale(domain=[y_min, y_max], zero=False), axis=None),
                text="label:N",
            )
            chart = chart + labels

    # Optional trader-toolkit overlays.
    line_specs = []
    if show_sma20:
        data["SMA 20"] = data["close"].rolling(20).mean(); line_specs.append(("SMA 20","#f0d98a"))
    if show_sma50:
        data["SMA 50"] = data["close"].rolling(50).mean(); line_specs.append(("SMA 50","#60a5fa"))
    if show_sma200:
        data["SMA 200"] = data["close"].rolling(200).mean(); line_specs.append(("SMA 200","#c084fc"))
    if show_ema9:
        data["EMA 9"] = data["close"].ewm(span=9, adjust=False).mean(); line_specs.append(("EMA 9","#fb923c"))
    if show_ema21:
        data["EMA 21"] = data["close"].ewm(span=21, adjust=False).mean(); line_specs.append(("EMA 21","#22d3ee"))
    if show_vwap and "volume" in data and data["volume"].fillna(0).sum() > 0:
        typical=(data["high"]+data["low"]+data["close"])/3
        data["VWAP"]=(typical*data["volume"]).cumsum()/data["volume"].cumsum().replace(0,np.nan)
        line_specs.append(("VWAP","#f472b6"))

    for name, color in line_specs:
        layer = alt.Chart(data).mark_line(color=color, strokeWidth=1.25).encode(
            x=x_enc, y=alt.Y(f"{name}:Q", scale=alt.Scale(domain=[y_min,y_max],zero=False), axis=None))
        chart = chart + layer

    if show_prev_day:
        d = data.set_index("timestamp").resample("1D").agg({"high":"max","low":"min"}).dropna()
        if len(d) >= 2:
            prev=d.iloc[-2]
            for val,color in [(prev["high"],"#7dd3fc"),(prev["low"],"#7dd3fc")]:
                chart += alt.Chart(pd.DataFrame({"price":[val]})).mark_rule(
                    color=color, strokeDash=[4,4], strokeWidth=1).encode(
                    y=alt.Y("price:Q",scale=alt.Scale(domain=[y_min,y_max],zero=False),axis=None))
    if show_prev_week:
        w = data.set_index("timestamp").resample("W").agg({"high":"max","low":"min"}).dropna()
        if len(w) >= 2:
            prev=w.iloc[-2]
            for val,color in [(prev["high"],"#a78bfa"),(prev["low"],"#a78bfa")]:
                chart += alt.Chart(pd.DataFrame({"price":[val]})).mark_rule(
                    color=color, strokeDash=[8,4], strokeWidth=1).encode(
                    y=alt.Y("price:Q",scale=alt.Scale(domain=[y_min,y_max],zero=False),axis=None))

    if state.current_price is not None:
        chart += alt.Chart(pd.DataFrame({"price":[state.current_price]})).mark_rule(
            color="#35c76f", opacity=.45, strokeDash=[2,2], strokeWidth=.7).encode(
            y=alt.Y("price:Q",scale=alt.Scale(domain=[y_min,y_max],zero=False),axis=None))

    # V2.9C: exact execution levels appear ONLY for canonical TRADE_READY.
    # This deliberately adds no lines for potential/armed/confirming candidates.
    trade = getattr(state, "trade", None)
    if str(getattr(state, "setup_state", "")).upper() == "TRADE_READY" and trade is not None:
        exact_rows = [
            {"price": float(trade.entry), "label": f"ENTRY {float(trade.entry):,.2f}", "kind": "ENTRY"},
            {"price": float(trade.stop), "label": f"STOP {float(trade.stop):,.2f}", "kind": "STOP"},
        ]
        for target in (getattr(trade, "targets", None) or [])[:3]:
            exact_rows.append({
                "price": float(target.price),
                "label": f"{target.name} {float(target.price):,.2f} / {float(target.rr_ratio):.1f}R",
                "kind": "TARGET",
            })

        edf = pd.DataFrame(exact_rows)
        exact_rules = alt.Chart(edf).mark_rule(strokeWidth=1.35).encode(
            y=alt.Y("price:Q", scale=alt.Scale(domain=[y_min,y_max],zero=False), axis=None),
            color=alt.Color(
                "kind:N",
                scale=alt.Scale(
                    domain=["ENTRY","STOP","TARGET"],
                    range=["#f0d98a","#ef4444","#35c76f"],
                ),
                legend=None,
            ),
            strokeDash=alt.condition(
                alt.datum.kind == "ENTRY",
                alt.value([1,0]),
                alt.value([6,4]),
            ),
        )
        last_ts = data["timestamp"].max()
        exact_labels_df = edf.copy()
        exact_labels_df["timestamp"] = last_ts
        exact_labels = alt.Chart(exact_labels_df).mark_text(
            align="right", dx=-8, dy=-6, fontSize=10, fontWeight="bold"
        ).encode(
            x=alt.X("timestamp:T", axis=None),
            y=alt.Y("price:Q", scale=alt.Scale(domain=[y_min,y_max],zero=False), axis=None),
            text="label:N",
            color=alt.Color(
                "kind:N",
                scale=alt.Scale(
                    domain=["ENTRY","STOP","TARGET"],
                    range=["#f0d98a","#ef4444","#35c76f"],
                ),
                legend=None,
            ),
        )
        chart = chart + exact_rules + exact_labels

    # Volume remains optional and deliberately subtle.
    if show_volume and "volume" in data and data["volume"].fillna(0).sum() > 0:
        volume = alt.Chart(data).mark_bar(opacity=.18).encode(
            x=x_enc, y=alt.Y("volume:Q", axis=None), color=alt.value("#64748b"))
        chart = alt.layer(chart, volume.resolve_scale(y="independent"))

    return (chart.properties(height=505, background=PANEL)
        .interactive()
        .configure_view(strokeOpacity=0)
        .configure_axis(gridColor="#28313d", gridOpacity=.18, labelFontSize=10))


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

if "zone_quality" not in st.session_state:
    st.session_state.zone_quality = "B"
for _key, _default in {
    "layer_context": False,
    "layer_execution": False,
    "layer_conflict": False,
    "layer_sma20": False,
    "layer_sma50": False,
    "layer_sma200": False,
    "layer_ema9": False,
    "layer_ema21": False,
    "layer_vwap": False,
    "layer_prev_day": False,
    "layer_prev_week": False,
    "layer_volume": False,
    "zone_grade_aplus": True,
    "zone_grade_a": True,
    "zone_grade_b": True,
    "zone_grade_c": True,
}.items():
    if _key not in st.session_state:
        st.session_state[_key] = _default

with st.spinner("Building canonical GC MarketState..."):
    try:
        market_state = get_market_state()
    except Exception as exc:
        st.error(f"Unable to build MarketState: {exc}")
        st.stop()

health, age_minutes = data_health(market_state.market_timestamp)
news_warning, news_level = get_news_state()


# ---------------------------------------------------------------------
# HEADER - BRANDED PRODUCTION BAR
# ---------------------------------------------------------------------

header_logo, header_title, header_price, header_feed = st.columns([1.65, 4.15, 1.0, 1.05], gap="small")
with header_logo:
    if BRAND_LOGO.exists():
        st.image(str(BRAND_LOGO), use_container_width=True)
    else:
        st.markdown(f"<div style='color:#d7b45a;font-weight:900'>{APP_NAME}</div>", unsafe_allow_html=True)

with header_title:
    st.markdown(
        f"""<div style="padding:5px 0 4px">
        <div class="tp-coach-name">{COACH_NAME}</div>
        <div class="tp-coach-sub">{DISPLAY_SYMBOL} / {MARKET_NAME} / FRONT-MONTH</div>
        </div>""",
        unsafe_allow_html=True,
    )

with header_price:
    st.markdown(
        f"<div style='text-align:right;color:#f5f7fa;font-size:1.05rem;font-weight:900;padding-top:12px'>{money(market_state.current_price)}</div>",
        unsafe_allow_html=True,
    )

with header_feed:
    feed_class = "green" if health == "CONNECTED" else "red"
    st.markdown(
        f"<div class='tp-feed-wrap' style='padding-top:14px'><span class='tp-feed-dot {feed_class}'></span>DATA FEED</div>",
        unsafe_allow_html=True,
    )

dashboard_tab, journal_tab, stats_tab, backtest_tab, system_tab = st.tabs(
    ["COMMAND CENTER", "JOURNAL", "PERFORMANCE", "BACKTEST", "SYSTEM"]
)

with dashboard_tab:
    # Top status strip.
    bias = str(market_state.market_bias or "--").upper()
    bias_cls = "tp-bull" if bias == "BULLISH" else "tp-bear" if bias == "BEARISH" else "tp-watch"
    state_txt = str(market_state.setup_state or "--").upper()
    direction = str(market_state.setup_direction or "--").upper()
    direction_cls = "tp-bull" if direction == "LONG" else "tp-bear" if direction == "SHORT" else "tp-dash"
    ready = bool(market_state.is_actionable)

    trend_values = [market_state.trends.get(k, "no_data") for _, k in TREND_DISPLAY_ORDER]
    valid_trends = [x for x in trend_values if x in ("bullish", "bearish", "neutral")]
    dominant = str(market_state.market_bias or "").lower()
    aligned = sum(x == dominant for x in valid_trends)
    total = len(valid_trends)
    align_pct = (aligned / total * 100.0) if total else 0.0
    heights = [12, 18, 24, 30, 36, 24, 18, 14]
    bars = "".join(f"<span style='height:{h}px'></span>" for h in heights)
    labels = "".join(f"<span>{label}</span>" for label, _ in TREND_DISPLAY_ORDER)

    st.markdown(f"""
    <div class="tp-status-grid">
      <div class="tp-status-cell"><div class="tp-status-label">BIAS</div>
        <div class="tp-status-value {bias_cls}">{bias}</div>
        <div class="tp-status-sub">Higher timeframe context</div></div>
      <div class="tp-status-cell"><div class="tp-status-label">SETUP STATE</div>
        <div class="tp-status-value tp-watch">{state_txt}</div>
        <div class="tp-status-sub">{'Qualified trigger' if ready else 'No confirmed trigger'}</div></div>
      <div class="tp-status-cell"><div class="tp-status-label">DIRECTION</div>
        <div class="tp-status-value {direction_cls}">{direction}</div>
        <div class="tp-status-sub">Preferred trade direction</div></div>
      <div class="tp-status-cell"><div class="tp-status-label">TRADE READY</div>
        <div class="tp-status-value {'tp-yes' if ready else 'tp-no'}">{'YES' if ready else 'NO'}</div>
        <div class="tp-status-sub">{'All requirements met' if ready else 'Requirements not met'}</div></div>
      <div class="tp-status-cell">
        <div class="tp-mtf-head">MTF ALIGNMENT</div>
        <div class="tp-mtf-big">{aligned} / {total if total else '--'}</div>
        <div class="tp-mtf-sub">{align_pct:.0f}% {bias.title()} directional agreement</div>
        <div class="tp-mini-bars">{bars}</div>
        <div class="tp-mini-labels">{labels}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.caption("MTF alignment is directional context only. Trade Ready still requires the full deterministic MarketState confirmation and risk rules.")

    # Cross-market watch strip. GC is the active full-analysis market.
    try:
        market_watch = get_market_watch()
    except Exception:
        market_watch = {}
    render_market_watch(market_watch)

    # Put chart timeframe controls immediately above the chart workspace.
    st.markdown(
        '<div class="tp-live-market-row"><div class="tp-command-kicker">PRICE ACTION</div>'
        '<div class="tp-command-name">Live Market</div></div>',
        unsafe_allow_html=True,
    )
    tf_cols = st.columns(len(CHART_TIMEFRAMES))
    for index, display_tf in enumerate(CHART_TIMEFRAMES.keys()):
        button_type = "primary" if st.session_state.chart_tf == display_tf else "secondary"
        if tf_cols[index].button(
            display_tf,
            use_container_width=True,
            type=button_type,
            key=f"tf_{display_tf}",
        ):
            st.session_state.chart_tf = display_tf
            st.rerun()

    selected_tf = st.session_state.chart_tf
    chart_col, intel_col, toolkit_col = st.columns([4.25, 1.35, 1.55], gap="small")

    with toolkit_col:
        with st.expander("TRADER TOOLKIT / CHART LAYERS", expanded=True):
            st.markdown("**POTENTIAL TRADE QUALITY**")
            st.session_state.zone_quality = st.selectbox(
                "Minimum Acceptable Grade",
                ["A+","A","B","C","ALL"],
                index=["A+","A","B","C","ALL"].index(st.session_state.zone_quality)
                    if st.session_state.zone_quality in ["A+","A","B","C","ALL"] else 2,
                help="Display-only learning filter. It shows developing supply/demand structure by quality without changing Trade Ready or MarketState.")

            st.caption("Potential structure visible on chart. These are NOT trade signals.")
            st.checkbox("A+ Zones (Highest Quality)", key="zone_grade_aplus")
            st.checkbox("A Zones (Good Quality)", key="zone_grade_a")
            st.checkbox("B Zones (Developing)", key="zone_grade_b")
            st.checkbox("C Zones (Weak / Potential)", key="zone_grade_c")

            st.caption("MarketState zones (OFF by default)")
            st.checkbox("HTF Context Zone", key="layer_context")
            st.checkbox("Execution Zone", key="layer_execution")
            st.checkbox("Active Conflict", key="layer_conflict")
            st.divider()
            st.markdown("**CHART LAYERS**")
            st.checkbox("SMA 20", key="layer_sma20")
            st.checkbox("SMA 50", key="layer_sma50")
            st.checkbox("SMA 200", key="layer_sma200")
            st.checkbox("EMA 9", key="layer_ema9")
            st.checkbox("EMA 21", key="layer_ema21")
            st.checkbox("VWAP", key="layer_vwap")
            st.checkbox("Previous Day High / Low", key="layer_prev_day")
            st.checkbox("Previous Week High / Low", key="layer_prev_week")
            st.checkbox("Volume", key="layer_volume")
            st.caption("Market sessions and swing-structure overlays are reserved for the next chart-engine pass.")

    with chart_col:
        st.markdown(
            f'<div class="tp-chart-head">{DISPLAY_SYMBOL} / {MARKET_NAME} &nbsp;&bull;&nbsp; {selected_tf}</div>',
            unsafe_allow_html=True)
        try:
            chart_df = get_chart_data(selected_tf, 260)
            if chart_df is not None and len(chart_df) >= 5:
                chart = build_candlestick_chart(
                    chart_df, selected_tf, market_state,
                    min_zone_grade=st.session_state.zone_quality,
                    show_context=st.session_state.layer_context,
                    show_execution=st.session_state.layer_execution,
                    show_conflict=st.session_state.layer_conflict,
                    show_sma20=st.session_state.layer_sma20,
                    show_sma50=st.session_state.layer_sma50,
                    show_sma200=st.session_state.layer_sma200,
                    show_ema9=st.session_state.layer_ema9,
                    show_ema21=st.session_state.layer_ema21,
                    show_vwap=st.session_state.layer_vwap,
                    show_prev_day=st.session_state.layer_prev_day,
                    show_prev_week=st.session_state.layer_prev_week,
                    show_volume=st.session_state.layer_volume,
                    show_grade_aplus=st.session_state.zone_grade_aplus,
                    show_grade_a=st.session_state.zone_grade_a,
                    show_grade_b=st.session_state.zone_grade_b,
                    show_grade_c=st.session_state.zone_grade_c,
                )
                if chart is not None:
                    st.altair_chart(chart, use_container_width=True)

                last_candle = chart_df.iloc[-1]
                o1,o2,o3,o4 = st.columns(4)
                o1.metric("OPEN", money(last_candle["open"]))
                o2.metric("HIGH", money(last_candle["high"]))
                o3.metric("LOW", money(last_candle["low"]))
                o4.metric("CLOSE", money(last_candle["close"]))

                note = f"{len(chart_df):,} candles / Minimum potential grade {st.session_state.zone_quality}"
                if selected_tf == "30m":
                    note += " / 30m resampled from 15m"
                st.markdown(f'<div class="tp-footnote">{note} / MarketState remains the source of truth.</div>',
                            unsafe_allow_html=True)
            else:
                st.warning(f"Not enough {selected_tf} data.")
        except Exception as exc:
            st.error(f"Chart error: {exc}")

    with intel_col:
        # V2.9A candidate intelligence uses the exact same grades shown on chart.
        candidates_29a = build_setup_candidates(market_state)
        enabled_29a = {
            "A+": st.session_state.zone_grade_aplus,
            "A": st.session_state.zone_grade_a,
            "B": st.session_state.zone_grade_b,
            "C": st.session_state.zone_grade_c,
            "D": False,
        }
        visible_29a = filter_candidates(
            candidates_29a,
            minimum_grade=st.session_state.zone_quality,
            enabled_grades=enabled_29a,
            limit=6,
        )
        st.markdown("**SETUP CANDIDATES / V2.9C**")
        counts = {g: sum(c.grade == g for c in candidates_29a) for g in ("A+", "A", "B", "C")}
        st.caption(
            f"Detected {len(candidates_29a)} / Visible {len(visible_29a)} | "
            f"A+ {counts['A+']} / A {counts['A']} / B {counts['B']} / C {counts['C']}"
        )
        if visible_29a:
            best = visible_29a[0]
            st.markdown(
                f"**{best.grade} {best.timeframe} {best.zone_type.upper()}**  "
                f"{money(best.lower_bound)} - {money(best.upper_bound)}"
            )
            best_execution = build_execution_lifecycle(market_state, best)
            st.caption(
                f"Setup {best.grade} {best.setup_score:.1f}/100 / Zone {best.zone_grade} {best.zone_quality_score:.1f}/100 / "
                f"{best_execution.stage} / Distance {best.distance_points:.2f} pts ({best.distance_percent:.3f}%)"
            )
            if best_execution.trade_ready:
                st.success(
                    f"TRADE READY / {best_execution.direction} / Entry {money(best_execution.entry)} / "
                    f"Stop {money(best_execution.stop)} / Grade {best_execution.setup_grade}"
                )
            elif best_execution.stage in ("ARMED", "CONFIRMING", "RISK_VALIDATING"):
                st.warning(f"{best_execution.stage.replace('_',' ')} / {best_execution.reason}")
            else:
                st.info(f"{best_execution.stage.replace('_',' ')} / {best_execution.reason}")
            with st.expander("Why this candidate has this grade"):
                for reason in best.reasons:
                    st.write(f"- {reason}")
                st.caption("Setup grade combines zone quality + timing/context. It is not win probability and cannot make Trade Ready true.")
            with st.expander("Structural planning preview", expanded=False):
                st.caption("STRUCTURAL PREVIEW ONLY — not an order. Exact entry/stop/targets unlock only when canonical status becomes TRADE READY.")
                p1,p2,p3 = st.columns(3)
                p1.metric("ZONE ENTRY", money(best.projected_entry))
                p2.metric("INVALIDATION", money(best.projected_stop))
                p3.metric("FIRST STRUCTURE", money(best.projected_target))
                if best.projected_rr is not None:
                    st.caption(f"Preview room: {best.projected_rr:.2f}R to nearest opposing structure. Trade Ready still controls execution.")
        else:
            st.caption("No candidates survive the current grade switches/filter.")

        execution = zone_dict(get_execution_zone(market_state))
        conflict = zone_dict(get_conflict_zone(market_state))

        if execution:
            st.markdown(f"""<div class="tp-intel-card">
              <div class="tp-intel-title green">EXECUTION ZONE ({execution.get('grade','--')})</div>
              <div class="tp-intel-value">{money(execution.get('lower_bound'))} - {money(execution.get('upper_bound'))}</div>
              <div class="tp-intel-detail">{execution.get('timeframe','--')} {str(execution.get('type','')).upper()} |
              Strength {safe_float(execution.get('strength'),0):.0f}/100<br>
              Distance {points(execution.get('distance_points'))} pts</div></div>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div class="tp-intel-card"><div class="tp-intel-title green">EXECUTION ZONE</div>
            <div class="tp-intel-value">--</div><div class="tp-intel-detail">No qualifying execution zone.</div></div>""",
                        unsafe_allow_html=True)

        if conflict:
            st.markdown(f"""<div class="tp-intel-card">
              <div class="tp-intel-title red">ACTIVE CONFLICT ({conflict.get('grade','--')})</div>
              <div class="tp-intel-value">{money(conflict.get('lower_bound'))} - {money(conflict.get('upper_bound'))}</div>
              <div class="tp-intel-detail">{conflict.get('timeframe','--')} {str(conflict.get('type','')).upper()} |
              Strength {safe_float(conflict.get('strength'),0):.0f}/100<br>
              Distance {points(conflict.get('distance_points'))} pts</div></div>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div class="tp-intel-card"><div class="tp-intel-title">ACTIVE CONFLICT</div>
            <div class="tp-intel-value">NONE</div><div class="tp-intel-detail">No opposing MarketState conflict.</div></div>""",
                        unsafe_allow_html=True)

        news_color = "red" if news_level == "HIGH" else "green" if news_level == "LOW" else ""
        st.markdown(f"""<div class="tp-intel-card"><div class="tp-intel-title {news_color}">NEWS IMPACT</div>
          <div class="tp-intel-value">{news_level}</div><div class="tp-intel-detail">{news_warning}</div></div>""",
                    unsafe_allow_html=True)
        if st.button("VIEW CALENDAR", use_container_width=True, key="cc_calendar"):
            st.session_state.show_cc_calendar = not st.session_state.get("show_cc_calendar", False)

        st.markdown("""<div class="tp-intel-card"><div class="tp-intel-title">HISTORICAL WIN RATE</div>
          <div class="tp-intel-value">INSUFFICIENT DATA</div>
          <div class="tp-intel-detail">Need 30+ comparable resolved historical samples. No probability is fabricated.</div></div>""",
                    unsafe_allow_html=True)

    if st.session_state.get("show_cc_calendar", False):
        st.divider()
        display_news_calendar()

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
        t1,t2,t3,t4 = st.columns(4)
        t1.metric("ENTRY", money(trade.entry))
        t2.metric("STOP", money(trade.stop))
        t3.metric("RISK / CONTRACT", money(trade.risk_dollars_per_contract))
        t4.metric("SETUP GRADE", trade.setup_grade or "--")
        if trade.targets:
            target_cols = st.columns(len(trade.targets))
            for idx,target in enumerate(trade.targets):
                target_cols[idx].metric(target.name, money(target.price), f"{target.rr_ratio:.1f}R")
        ready_candidates = build_setup_candidates(market_state)
        selected_candidate = next((c for c in ready_candidates if c.is_selected_zone), None)
        execution_snapshot = build_execution_lifecycle(market_state, selected_candidate)
        st.success("BROKER GATE: ELIGIBLE FOR FUTURE ORDER ADAPTER — account risk/quantity authorization still required.")
        with st.expander("Broker-ready deterministic order packet", expanded=False):
            st.json(broker_order_intent(market_state, selected_candidate), expanded=False)

    with st.expander("MARKET STRUCTURE / MULTI-TIMEFRAME DETAIL", expanded=False):
        trend_cols = st.columns(len(TREND_DISPLAY_ORDER))
        for index,(label,key) in enumerate(TREND_DISPLAY_ORDER):
            trend = market_state.trends.get(key,"no_data")
            trend_cols[index].metric(label, str(trend).upper().replace("_"," "))

    with st.expander("PROFESSOR / MARKET INTELLIGENCE", expanded=False):
        render_professor_bridge(market_state)


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
        THE TRADING PULSE / GOLD TRADING COACH V2.9A /
        CANONICAL MARKETSTATE ARCHITECTURE /
        EDUCATIONAL MARKET-ANALYSIS SOFTWARE / NOT FINANCIAL ADVICE
    </div>
    """,
    unsafe_allow_html=True,
)
