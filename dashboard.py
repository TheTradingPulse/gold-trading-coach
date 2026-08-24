"""
THE TRADING PULSE
Gold Trading Coach V2 FINAL CRITICAL CHART FIX Dashboard

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

import os
import sys
from pathlib import Path
from datetime import datetime
from io import StringIO

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import json

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
from journal_tracker import add_candidate_to_journal, refresh_tracked_trades, ensure_tracking_schema
from dna_engine import analyze_dna_performance
from news_engine import generate_news_warning, display_news_calendar
from backtest_engine import run_backtest, get_available_years
from backtest_lab_engine import evidence_stats, recent_experiments, TF_SETS
from market_watch_engine import fetch_market_watch
from multi_market_elite_engine import scan_elite_snapshot, ELITE_MIN_SCORE, WATCH_MIN_SCORE
from live_grading_service import grade_live_candidate, has_live_star
from data_truth_service import truth_status, allow_manual_backtest
from instruments import get_instrument, get_enabled_symbols
from professor_engine import (
    academy_lessons, answer_question, get_pending_professor_claims,
    get_professor_metrics, get_recent_professor_questions,
    professor_research_available, rate_professor_answer, review_professor_claim,
)


# ---------------------------------------------------------------------
# PAGE
# ---------------------------------------------------------------------

st.set_page_config(
    page_title="The Trading Pulse | Gold",
    page_icon="TP",
    layout="wide",
    initial_sidebar_state="collapsed",
)

AUTO_REFRESH_SECONDS = max(60, int(os.getenv("TP_AUTO_REFRESH_SECONDS", "120")))
if os.getenv("TP_AUTO_REFRESH_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}:
    st_autorefresh(interval=AUTO_REFRESH_SECONDS * 1000, key="tp_auto_refresh")


# ---------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------

APP_NAME = "THE TRADING PULSE"
COACH_NAME = "FUTURES TRADING COACH"
DISPLAY_SYMBOL = "GC"
MARKET_NAME = "GOLD FUTURES"
# Trading Pulse design system - single source of truth for application color.
# Brand: near-black surfaces + Pulse red. Semantic colors are reserved for meaning.
BRAND = "#ff4b55"
BRAND_HOVER = "#e33f49"
BRAND_SOFT = "#ff7a82"
ACCENT = BRAND
ACCENT_SOFT = BRAND_SOFT
BG = "#07090d"
PANEL = "#0d1118"
PANEL_2 = "#111722"
BORDER = "#242c39"
TEXT = "#f5f7fa"
MUTED = "#b3bdcb"
GREEN = "#22c55e"
RED = "#ef4444"
BLUE = "#3b82f6"
AMBER = BLUE  # A+ RC: neutral informational accent; no amber/gold UI accent

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
        color: #ff6b74;
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
        --tp-brand: {ACCENT};
        --tp-brand-soft: {ACCENT_SOFT};
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
        background: linear-gradient(90deg, transparent, var(--tp-brand), transparent);
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
        color: var(--tp-brand-soft);
        font-weight: 900;
        letter-spacing: -.06em;
        background: linear-gradient(145deg, rgba(215,180,90,.13), rgba(255,255,255,.015));
        box-shadow: 0 0 30px rgba(215,180,90,.08);
    }}

    .tp-eyebrow {{
        color: var(--tp-brand);
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
        color: var(--tp-brand);
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
        color: var(--tp-brand-soft);
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
        color: var(--tp-brand-soft);
        transform: translateY(-1px);
    }}

    div[data-testid="stButton"] > button[kind="primary"] {{
        background: linear-gradient(135deg, #ff4b55, #c9323d);
        color: #080a0d;
        border-color: #ff4b55;
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
        color: var(--tp-brand-soft) !important;
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


    /* Premium interface cleanup */
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


    /* Command Center layout */
    .block-container {{ max-width: 1900px; padding-left: 1.45rem; padding-right: 1.45rem; }}
    .tp-topline, .tp-hero, .tp-brand-row {{ }}
    .tp-command-title {{ margin: 2px 0 10px 0; }}
    .tp-command-kicker {{ color:#ff4b55; font-size:.66rem; font-weight:850; letter-spacing:.16em; }}
    .tp-command-name {{ color:#f5f7fa; font-size:1.08rem; font-weight:850; margin-top:4px; }}
    .tp-status-grid {{
        display:grid; grid-template-columns: repeat(5,minmax(0,1fr));
        border:1px solid #36404e; border-radius:9px; overflow:hidden;
        background:linear-gradient(145deg,#10161f,#0a0f16); margin:12px 0 12px 0;
    }}
    .tp-status-cell {{ min-height:68px; padding:10px 14px 9px; border-right:1px solid #2b3440; }}
    .tp-status-cell:last-child {{ border-right:none; }}
    .tp-status-label {{ color:#d5dae3; font-size:.72rem; font-weight:800; letter-spacing:.04em; }}
    .tp-status-value {{ font-size:1.12rem; font-weight:900; margin-top:5px; letter-spacing:.01em; }}
    .tp-status-sub {{ color:#aab4c2; font-size:.66rem; margin-top:4px; }}
    .tp-bull {{ color:#35c76f; }} .tp-bear {{ color:#ff4d57; }}
    .tp-watch {{ color:#7ea6d8; }} .tp-no {{ color:#ff4d57; }} .tp-yes {{ color:#35c76f; }}
    .tp-dash {{ color:#8993a1; }}
    .tp-panelbox {{
        border:1px solid #36404e; border-radius:9px;
        background:linear-gradient(145deg,#10161f,#0a0f16); padding:15px 16px;
    }}
    .tp-mtf-head {{ color:#aeb8c6; font-size:.72rem; letter-spacing:.08em; font-weight:800; }}
    .tp-mtf-big {{ color:#35c76f; font-size:1.22rem; font-weight:900; margin-top:4px; }}
    .tp-mtf-sub {{ color:#c6ccd5; font-size:.73rem; margin-top:3px; }}
    .tp-mini-bars {{ height:24px; display:flex; align-items:flex-end; gap:9px; margin-top:3px; }}
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
    .tp-feed-dot.amber {{ background:#7ea6d8; box-shadow:0 0 10px rgba(126,166,216,.30); }}
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
        background:linear-gradient(180deg,#ff6670,#c93442); border-color:#ff6670;
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

    
    .tp-hero-card {{background:linear-gradient(110deg,#101720 0%,#1d1118 100%);border:1px solid #2a3441;border-radius:14px;padding:18px 20px;min-height:112px;}}
    .tp-hero-kicker {{color:#ff4b55;font-size:.66rem;font-weight:900;letter-spacing:.18em;margin-bottom:5px;}}
    .tp-hero-title {{color:#f7f8fa;font-size:2rem;font-weight:950;line-height:1.05;}}
    .tp-hero-tagline {{color:#f0f2f5;font-size:.90rem;margin-top:8px;}}
    .tp-hero-sub {{color:#9aa6b5;font-size:.72rem;margin-top:5px;letter-spacing:.06em;}}
    .tp-mini-card {{background:#0f151d;border:1px solid #2b3745;border-radius:14px;padding:18px 16px;min-height:112px;}}
    .tp-mini-label {{color:#aeb8c6;font-size:.72rem;letter-spacing:.08em;}}
    .tp-mini-value {{color:#d7deea;font-size:1.55rem;font-weight:900;margin-top:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}

    /* White-glove layout polish */
    .block-container {{ max-width:1760px !important; padding:1.05rem 1.15rem 2.5rem !important; }}
    .tp-hero-card {{ min-height:96px !important; padding:15px 20px !important; border-radius:10px !important; }}
    .tp-hero-title {{ font-size:1.72rem !important; }}
    .tp-hero-tagline {{ margin-top:6px !important; font-size:.82rem !important; }}
    .tp-hero-sub {{ font-size:.64rem !important; }}
    .tp-status-grid {{ margin:10px 0 8px !important; border-radius:8px !important; }}
    .tp-status-cell {{ min-height:54px !important; padding:8px 12px 7px !important; }}
    .tp-status-value {{ font-size:1.02rem !important; margin-top:4px !important; line-height:1.05 !important; }}
    .tp-status-sub {{ margin-top:3px !important; font-size:.58rem !important; line-height:1.15 !important; }}
    .tp-mtf-big {{ font-size:1.05rem !important; margin-top:3px !important; line-height:1.05 !important; }}
    .tp-mini-bars {{ height:14px !important; margin-top:3px !important; }}
    .tp-mini-bars span {{ width:10px !important; max-height:14px !important; }}
    .tp-status-label, .tp-mtf-head {{ font-size:.60rem !important; }}
    .tp-mtf-sub {{ font-size:.58rem !important; margin-top:2px !important; }}
    .tp-mini-labels {{ font-size:.50rem !important; margin-top:2px !important; }}
    .tp-market-watch-wrap {{ margin:8px 0 12px !important; padding:9px 10px 10px !important; }}
    .tp-market-card {{ padding:8px !important; }}
    .tp-market-price {{ font-size:.82rem !important; }}
    .tp-chart-head {{ padding:10px 13px !important; }}
    .tp-intel-card {{ padding:12px 13px !important; margin-bottom:9px !important; min-height:0 !important; }}
    .tp-intel-value {{ font-size:.98rem !important; margin-top:7px !important; }}
    .tp-intel-detail {{ font-size:.64rem !important; margin-top:5px !important; }}
    div[data-testid="stMetric"] {{ padding:10px 12px !important; }}
    div[data-testid="stMetricValue"] {{ font-size:1.30rem !important; }}
    div[data-testid="stVerticalBlock"] {{ gap:.65rem; }}
    .tp-radar-card {{
        border:1px solid rgba(215,180,90,.34);
        background:linear-gradient(90deg,rgba(215,180,90,.10),rgba(13,17,24,.82));
        border-radius:8px;padding:10px 13px;margin:6px 0 12px;
        display:flex;justify-content:space-between;gap:18px;align-items:center;
    }}
    .tp-radar-main {{ color:#f4f6f9;font-size:.76rem;font-weight:800; }}
    .tp-radar-sub {{ color:#8f9aaa;font-size:.62rem;margin-top:3px; }}
    .tp-radar-count {{ color:#ff4b55;font-size:.72rem;font-weight:900;white-space:nowrap; }}
    .tp-section-rule {{ border-top:1px solid rgba(255,255,255,.06);margin:10px 0 8px; }}
    @media (max-width:1200px) {{ .tp-status-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)) !important; }} }}


    /* Global control styling: primary actions use Trading Pulse red. */
    div[data-testid="stButton"] > button[kind="primary"],
    div[data-testid="stDownloadButton"] > button[kind="primary"] {{
        background: linear-gradient(180deg, var(--tp-brand-soft), var(--tp-brand)) !important;
        color: #ffffff !important;
        border: 1px solid var(--tp-brand-soft) !important;
        box-shadow: 0 0 16px rgba(255,75,85,.16) !important;
    }}
    div[data-testid="stButton"] > button[kind="primary"]:hover,
    div[data-testid="stDownloadButton"] > button[kind="primary"]:hover {{
        filter: brightness(1.08);
        border-color: #ff9aa0 !important;
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


def score10(value):
    """Convert the deterministic 0-100 setup score to the trader-facing 0-10 scale."""
    value = safe_float(value)
    return "--" if value is None else f"{value / 10.0:.1f}/10"


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
    """Yahoo is a delayed/reference feed, so never label it exchange-real-time LIVE."""
    if timestamp_value is None:
        return "DISCONNECTED", None
    try:
        ts = pd.Timestamp(timestamp_value)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        now = pd.Timestamp.now(tz="UTC")
        age_minutes = max(0.0, (now - ts).total_seconds() / 60.0)
        if age_minutes <= 45:
            return "DELAYED", age_minutes
        return "STALE", age_minutes
    except Exception:
        return "DISCONNECTED", None


def get_news_state():
    try:
        warning, level = generate_news_warning()
        return warning, level
    except Exception:
        return "Economic-event status unavailable.", "UNKNOWN"


@st.cache_data(ttl=110, show_spinner=False)
def get_market_watch():
    return fetch_market_watch(MARKET_WATCH_ORDER)


def render_market_watch(cards):
    """Compact scanner: price/change only. Tiny sparklines were removed as non-decision-useful."""
    cards = cards or {}
    html = [
        '<div class="tp-market-watch-wrap">',
        '<div class="tp-market-watch-head">',
        '<div class="tp-market-watch-title">MARKET WATCH</div>',
        '<div class="tp-market-watch-sub">Reference market data / select a symbol below to switch markets</div>',
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
        active = " active" if symbol == st.session_state.get("active_symbol", "GC") else ""
        dot_cls = "up" if change > 0 else "down" if change < 0 else ""
        price_text = "--" if price is None else f"{price:,.2f}"
        change_text = "--" if price is None else f"{change:+,.2f} ({pct:+.2f}%)"
        html.extend([
            f'<div class="tp-market-card{active}" title="{symbol} / {meta_name}">',
            '<div class="tp-market-top">',
            f'<div class="tp-market-symbol">{symbol}</div>',
            f'<span class="tp-market-dot {dot_cls}"></span>',
            '</div>',
            f'<div class="tp-market-name">{meta_name}</div>',
            f'<div class="tp-market-price">{price_text}</div>',
            f'<div class="tp-market-change {direction}">{change_text}</div>',
            '</div>',
        ])
    html.extend([
        '</div>',
        '<div class="tp-market-note">Market Watch, charts, setup analysis and journal use the same Trading Pulse market data.</div>',
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


@st.cache_data(ttl=60, show_spinner=False)
def get_chart_data(display_tf, limit=260, symbol="GC"):
    db_tf = CHART_TIMEFRAMES[display_tf]
    if display_tf == "30m":
        raw = load_market_data("15m", limit=limit * 2 + 20, symbol=symbol)
        return resample_30m(raw)
    return load_market_data(db_tf, limit=limit, symbol=symbol)


@st.cache_data(ttl=45, show_spinner=False)
def get_market_state(symbol="GC"):
    return build_market_state(symbol)


@st.cache_data(ttl=110, show_spinner=False)
def get_global_elite_snapshot():
    """Global Elite board plus explainable funnel diagnostics from one shared scan."""
    return scan_elite_snapshot(get_enabled_symbols(), limit=6)


@st.cache_data(ttl=60, show_spinner=False)
def get_evidence_stats():
    return evidence_stats()


@st.cache_data(ttl=60, show_spinner=False)
def get_recent_experiments(limit=5):
    return recent_experiments(limit)


@st.cache_data(ttl=30, show_spinner=False)
def get_professor_metrics_cached():
    return get_professor_metrics()


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
                    No qualifying {role.lower()} zone is currently available.
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


def projected_targets_for_candidate(candidate, state, limit=2):
    """Return conservative structural target edges for a potential setup.

    These are planning levels only. Canonical TradeState remains the only source
    of executable targets after confirmation and risk validation.
    """
    if candidate is None:
        return []
    entry = safe_float(getattr(candidate, "projected_entry", None))
    if entry is None:
        return []
    rows = []
    if str(candidate.zone_type).lower() == "demand":
        for zone in (getattr(state, "supply_zones", None) or []):
            price = safe_float(getattr(zone, "lower_bound", None))
            if price is not None and price > entry:
                rows.append(price)
        rows.sort()
    else:
        for zone in (getattr(state, "demand_zones", None) or []):
            price = safe_float(getattr(zone, "upper_bound", None))
            if price is not None and price < entry:
                rows.append(price)
        rows.sort(reverse=True)
    deduped = []
    for price in rows:
        if not deduped or abs(price - deduped[-1]) > max(abs(entry) * 0.0005, 0.5):
            deduped.append(price)
        if len(deduped) >= limit:
            break
    return deduped


def planned_trade_metrics(candidate, market_state):
    """Display-only planning math for GC. Never changes TRADE_READY or broker eligibility."""
    entry = safe_float(getattr(candidate, "projected_entry", None))
    stop = safe_float(getattr(candidate, "projected_stop", None))
    targets = projected_targets_for_candidate(candidate, market_state, limit=2)
    t1 = safe_float(targets[0]) if len(targets) > 0 else None
    t2 = safe_float(targets[1]) if len(targets) > 1 else None
    if entry is None or stop is None:
        return {"entry": entry, "stop": stop, "t1": t1, "t2": t2}
    point_risk = abs(entry - stop)
    # GC standard COMEX contract = $100 per 1.00 price point.
    dollars_per_point = 100.0
    risk_dollars = point_risk * dollars_per_point
    def rr_and_return(target):
        if target is None or point_risk <= 0:
            return None, None
        reward_points = abs(target - entry)
        return reward_points / point_risk, reward_points * dollars_per_point
    rr1, ret1 = rr_and_return(t1)
    rr2, ret2 = rr_and_return(t2)
    return {
        "entry": entry, "stop": stop, "t1": t1, "t2": t2,
        "risk_points": point_risk, "risk_dollars": risk_dollars,
        "rr1": rr1, "rr2": rr2, "return1": ret1, "return2": ret2,
    }

# ---------------------------------------------------------------------
# CHART
# ---------------------------------------------------------------------

def render_tradingview_lightweight_chart(
    df,
    timeframe_label,
    state,
    focused_candidate_id=None,
    candidates=None,
    show_context=True,
    show_execution=True,
    show_conflict=True,
    show_sma20=False,
    show_sma50=False,
    show_sma200=False,
    show_ema9=False,
    show_ema21=False,
    show_vwap=False,
    show_volume=False,
):
    # TradingView visual renderer; Trading Pulse remains authoritative for all trade values.
    if df is None or len(df) < 2:
        return False

    work = df.copy().tail(320)
    if not isinstance(work.index, pd.DatetimeIndex):
        work.index = pd.to_datetime(work.index, utc=True)
    else:
        if work.index.tz is None:
            work.index = work.index.tz_localize("UTC")
        else:
            work.index = work.index.tz_convert("UTC")

    for col in ["open", "high", "low", "close", "volume"]:
        if col in work.columns:
            work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=["open", "high", "low", "close"])
    if len(work) < 2:
        return False

    candles = []
    for ts, row in work.iterrows():
        candles.append({
            "time": int(ts.timestamp()),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        })

    def line_values(series):
        vals=[]
        for ts, value in series.dropna().items():
            vals.append({"time": int(ts.timestamp()), "value": float(value)})
        return vals

    indicators=[]
    close=work["close"]
    if show_sma20:
        indicators.append({"name":"SMA 20","color":"#7ea6d8","data":line_values(close.rolling(20).mean())})
    if show_sma50:
        indicators.append({"name":"SMA 50","color":"#a78bfa","data":line_values(close.rolling(50).mean())})
    if show_sma200:
        indicators.append({"name":"SMA 200","color":"#94a3b8","data":line_values(close.rolling(200).mean())})
    if show_ema9:
        indicators.append({"name":"EMA 9","color":"#60a5fa","data":line_values(close.ewm(span=9, adjust=False).mean())})
    if show_ema21:
        indicators.append({"name":"EMA 21","color":"#c084fc","data":line_values(close.ewm(span=21, adjust=False).mean())})
    if show_vwap and "volume" in work.columns:
        vol=work["volume"].fillna(0)
        typical=(work["high"]+work["low"]+work["close"])/3.0
        denom=vol.cumsum().replace(0, np.nan)
        indicators.append({"name":"VWAP","color":"#38bdf8","data":line_values((typical*vol).cumsum()/denom)})

    levels=[]
    def add_level(price, title, color, style=2, width=1):
        price=safe_float(price)
        if price is not None:
            levels.append({"price":float(price),"title":str(title),"color":color,"style":style,"width":width})

    def add_zone(zone, title, color):
        z=zone_dict(zone)
        if not z:
            return
        add_level(z.get("upper_bound"), f"{title} HIGH", color, 2, 1)
        add_level(z.get("lower_bound"), f"{title} LOW", color, 2, 1)

    if show_context:
        add_zone(get_context_zone(state), "CONTEXT", "#64748b")
    if show_execution:
        add_zone(get_execution_zone(state), "EXECUTION", "#3b82f6")
    if show_conflict:
        add_zone(get_conflict_zone(state), "CONFLICT", "#ef4444")

    all_candidates = candidates if candidates is not None else build_setup_candidates(state)
    selected = None
    if focused_candidate_id:
        selected = next((c for c in all_candidates if c.candidate_id == focused_candidate_id), None)
    if selected is not None:
        zone_color = "#22c55e" if str(selected.zone_type).lower()=="demand" else "#ef4444"
        add_level(selected.upper_bound, f"{selected.timeframe} {str(selected.zone_type).upper()} HIGH", zone_color, 3, 2)
        add_level(selected.lower_bound, f"{selected.timeframe} {str(selected.zone_type).upper()} LOW", zone_color, 3, 2)
        add_level(getattr(selected,"projected_entry",None), "PLANNED ENTRY", "#3b82f6", 0, 2)
        add_level(getattr(selected,"projected_stop",None), "PLANNED STOP", "#ef4444", 2, 2)
        for idx, target in enumerate(projected_targets_for_candidate(selected, state, limit=2), 1):
            add_level(target, f"TARGET {idx}", "#22c55e", 2, 2)

    trade=getattr(state,"trade",None)
    if str(getattr(state,"setup_state","")).upper()=="TRADE_READY" and trade is not None:
        add_level(getattr(trade,"entry",None), "ENTRY", "#3b82f6", 0, 2)
        add_level(getattr(trade,"stop",None), "STOP", "#ef4444", 2, 2)
        for target in (getattr(trade,"targets",None) or [])[:3]:
            add_level(getattr(target,"price",None), getattr(target,"name","TARGET"), "#22c55e", 2, 2)

    volume=[]
    if show_volume and "volume" in work.columns:
        for ts,row in work.iterrows():
            v=safe_float(row.get("volume"),0.0) or 0.0
            volume.append({"time":int(ts.timestamp()),"value":float(v),"color":"rgba(34,197,94,.28)" if row["close"]>=row["open"] else "rgba(239,68,68,.28)"})

    payload=json.dumps({"candles":candles,"levels":levels,"indicators":indicators,"volume":volume}, separators=(",",":"))
    html=f'''<!doctype html><html><head><meta charset="utf-8"><style>
html,body,#chart{{margin:0;width:100%;height:100%;background:#07090d;overflow:hidden}}
#wrap{{height:720px;border:1px solid #36404e;border-radius:0 0 9px 9px;overflow:hidden;background:#07090d}}
#chart{{height:100%}}
#badge{{position:absolute;z-index:5;left:12px;top:10px;background:rgba(7,9,13,.78);border:1px solid #242c39;border-radius:7px;padding:6px 9px;color:#9fa9b7;font:600 11px system-ui;pointer-events:none}}
</style></head><body><div id="wrap"><div id="badge">TRADINGVIEW CHART ENGINE &bull; {timeframe_label} &bull; YAHOO DELAYED REFERENCE DATA</div><div id="chart"></div></div>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<script>
const payload={payload};
const root=document.getElementById('chart');
if(!window.LightweightCharts){{root.innerHTML='<div style="color:#cbd5e1;padding:24px;font:14px system-ui">TradingView chart library could not load. Check internet access and refresh.</div>';}}
else{{
const chart=LightweightCharts.createChart(root,{{layout:{{background:{{type:'solid',color:'#07090d'}},textColor:'#b3bdcb'}},grid:{{vertLines:{{color:'#111722'}},horzLines:{{color:'#18212c'}}}},rightPriceScale:{{borderColor:'#242c39'}},timeScale:{{borderColor:'#242c39',timeVisible:true,secondsVisible:false,rightOffset:8,barSpacing:8,minBarSpacing:3}},crosshair:{{mode:LightweightCharts.CrosshairMode.Normal}},localization:{{priceFormatter:p=>'$'+Number(p).toLocaleString(undefined,{{minimumFractionDigits:2,maximumFractionDigits:2}})}}}});
const candles=chart.addCandlestickSeries({{upColor:'#22c55e',downColor:'#ef4444',borderUpColor:'#22c55e',borderDownColor:'#ef4444',wickUpColor:'#22c55e',wickDownColor:'#ef4444',priceLineVisible:true,lastValueVisible:true}});
candles.setData(payload.candles);
for(const lv of payload.levels){{candles.createPriceLine({{price:lv.price,color:lv.color,lineWidth:lv.width,lineStyle:lv.style,axisLabelVisible:true,title:lv.title}});}}
for(const ind of payload.indicators){{const line=chart.addLineSeries({{color:ind.color,lineWidth:1,priceLineVisible:false,lastValueVisible:false,title:ind.name}});line.setData(ind.data);}}
if(payload.volume.length){{const vol=chart.addHistogramSeries({{priceFormat:{{type:'volume'}},priceScaleId:'vol',lastValueVisible:false,priceLineVisible:false}});vol.priceScale().applyOptions({{scaleMargins:{{top:.82,bottom:0}}}});vol.setData(payload.volume);}}
chart.timeScale().fitContent();
const ro=new ResizeObserver(()=>chart.applyOptions({{width:root.clientWidth,height:root.clientHeight}}));ro.observe(root);
}}
</script></body></html>'''
    components.html(html, height=724, scrolling=False)
    return True


def build_candlestick_chart(
    df,
    timeframe_label,
    state,
    min_zone_grade="ALL",
    show_context=True,
    show_execution=True,
    show_conflict=True,
    show_htf_supply=False,
    show_ltf_supply=False,
    show_htf_demand=False,
    show_ltf_demand=False,
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
    focused_candidate_id=None,
    candidates=None,
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

    # Reference-feed timestamps can be delayed/misaligned. Hide the time axis in V2.
    # A broker/exchange live chart will replace this visual layer in V3.
    x_enc = alt.X("timestamp:T", axis=None)
    y_enc = alt.Y("low:Q", scale=alt.Scale(domain=[y_min, y_max], zero=False),
        axis=alt.Axis(title="PRICE", orient="right", labelColor="#c9d2df", titleColor="#8f9baa",
                      tickColor=BORDER, domainColor=BORDER, format="$,.2f", grid=True, gridColor="#18212c",
                      gridOpacity=.45, tickCount=8))
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

    # V2.12: chart grades are SETUP grades from the canonical Setup Candidate Engine.
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

    # V2.10D: the chart shows setups belonging to the ACTIVE timeframe only.
    # This prevents a 5m chart from being covered by 1H/4H/D candidate labels.
    tf_map = {"1D": "D", "1W": "W"}
    active_tf = tf_map.get(timeframe_label, timeframe_label)
    relevant_tfs = {active_tf}

    # V3.4 Pass 2B: consume the canonical candidate set created once per rerun.
    all_candidates = candidates if candidates is not None else build_setup_candidates(state)
    visible_candidates = filter_candidates(
        all_candidates,
        minimum_grade=min_zone_grade,
        enabled_grades=grade_switches,
        relevant_timeframes=relevant_tfs,
        limit=12,
    )

    # Legacy foundation: four research-zone toggles expose canonical setup-candidate zones by
    # timeframe family and side. Setup Quality buttons above control which grades
    # are eligible, so the two control groups work together instead of duplicating
    # MarketState cards.
    zone_toggle_candidates = filter_candidates(
        all_candidates,
        minimum_grade=min_zone_grade,
        enabled_grades=grade_switches,
        relevant_timeframes={"1m", "5m", "15m", "30m", "1H", "4H", "D", "W"},
        limit=40,
    )
    high_tfs = {"1H", "4H", "D", "W"}
    low_tfs = {"1m", "5m", "15m", "30m"}
    for candidate in zone_toggle_candidates:
        tf = str(candidate.timeframe)
        ztype = str(candidate.zone_type).lower()
        enabled = (
            (show_htf_supply and tf in high_tfs and ztype == "supply") or
            (show_ltf_supply and tf in low_tfs and ztype == "supply") or
            (show_htf_demand and tf in high_tfs and ztype == "demand") or
            (show_ltf_demand and tf in low_tfs and ztype == "demand")
        )
        if enabled:
            zone_rows.append({
                "lower": candidate.lower_bound,
                "upper": candidate.upper_bound,
                "zone_role": f"{tf} {ztype.title()}",
                "grade": candidate.grade,
                "zone_grade": candidate.zone_grade,
                "setup_score": candidate.setup_score,
                "distance": candidate.distance_percent,
                "timeframe": candidate.timeframe,
                "candidate_label": f"{candidate.setup_score / 10.0:.1f}/10 / {tf} {ztype.upper()}",
            })

    # V2 FINAL CRITICAL UX: the chart opens clean. Candidate overlays appear ONLY
    # after the user explicitly selects a setup. Never auto-pick the first setup.
    if focused_candidate_id:
        display_candidates = [c for c in visible_candidates if c.candidate_id == focused_candidate_id]
    else:
        display_candidates = []

    for candidate in display_candidates:
        zone_rows.append({
            "lower": candidate.lower_bound,
            "upper": candidate.upper_bound,
            "zone_role": "Potential Demand" if candidate.zone_type == "demand" else "Potential Supply",
            "grade": candidate.grade,
            "zone_grade": candidate.zone_grade,
            "setup_score": candidate.setup_score,
            "distance": candidate.distance_percent,
            "timeframe": candidate.timeframe,
            "candidate_label": f"{candidate.setup_score / 10.0:.1f}/10 SETUP / {candidate.timeframe} {candidate.zone_type.upper()} / {candidate.lifecycle}",
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
        chart = chart + zone_layer

        # Label potential zones with the SAME V2.12 grade/lifecycle used by the filter.
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
        data["SMA 20"] = data["close"].rolling(20).mean(); line_specs.append(("SMA 20",BLUE))
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

    # V2.10B: show the best visible candidate's PLANNED entry/stop/targets.
    # These lines are informational planning levels, never broker/order intent.
    if focused_candidate_id and display_candidates:
        planned_candidate = display_candidates[0]
        planned_targets = projected_targets_for_candidate(planned_candidate, state, limit=2)
        planned_rows = []
        if planned_candidate.projected_entry is not None:
            planned_rows.append({"price": float(planned_candidate.projected_entry), "label": f"PLANNED ENTRY {float(planned_candidate.projected_entry):,.2f}", "kind": "ENTRY"})
        if planned_candidate.projected_stop is not None:
            planned_rows.append({"price": float(planned_candidate.projected_stop), "label": f"PLANNED STOP {float(planned_candidate.projected_stop):,.2f}", "kind": "STOP"})
        for idx, target_price in enumerate(planned_targets, start=1):
            planned_rows.append({"price": float(target_price), "label": f"PLANNED T{idx} {float(target_price):,.2f}", "kind": "TARGET"})
        if planned_rows and str(getattr(state, "setup_state", "")).upper() != "TRADE_READY":
            pdf = pd.DataFrame(planned_rows)
            planned_rules = alt.Chart(pdf).mark_rule(strokeWidth=1.05, opacity=.72, strokeDash=[4,4]).encode(
                y=alt.Y("price:Q", scale=alt.Scale(domain=[y_min,y_max],zero=False), axis=None),
                color=alt.Color("kind:N", scale=alt.Scale(domain=["ENTRY","STOP","TARGET"], range=[BLUE,RED,GREEN]), legend=None),
            )
            last_ts = data["timestamp"].max()
            pldf = pdf.copy(); pldf["timestamp"] = last_ts
            planned_labels = alt.Chart(pldf).mark_text(align="right", dx=-8, dy=-6, fontSize=9, fontWeight="bold", opacity=.86).encode(
                x=alt.X("timestamp:T", axis=None),
                y=alt.Y("price:Q", scale=alt.Scale(domain=[y_min,y_max],zero=False), axis=None),
                text="label:N",
                color=alt.Color("kind:N", scale=alt.Scale(domain=["ENTRY","STOP","TARGET"], range=[BLUE,RED,GREEN]), legend=None),
            )
            chart = chart + planned_rules + planned_labels

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
                    range=[BLUE,RED,GREEN],
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
                    range=[BLUE,RED,GREEN],
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

    return (chart.properties(height=650, background=PANEL)
        .interactive()
        .configure_view(strokeOpacity=0)
        .configure_axis(gridColor="#28313d", gridOpacity=.22, labelFontSize=11, titleFontSize=11))


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


def render_trade_readiness(state):
    """Compact deterministic execution-readiness view.

    UI only: the canonical validation/scoring logic remains in MarketState.
    The same state is intentionally preserved for the future Professor bridge.
    """
    checks = setup_checks(state)
    completed = sum(1 for done, _ in checks if done)
    total = max(len(checks), 1)

    short_names = ["BIAS", "ZONE", "ENTRY", "CONFIRM", "TRIGGER", "RISK"]
    status_cols = st.columns(len(checks) if checks else 1)

    st.markdown(
        f"<div style='display:flex;align-items:baseline;gap:12px;margin-bottom:8px'>"
        f"<span style='font-size:1.35rem;font-weight:900;color:#f3f5f7'>TRADE READINESS</span>"
        f"<span style='font-size:.78rem;font-weight:900;color:#ff4b55;letter-spacing:.08em'>"
        f"{completed} OF {len(checks)} CONFIRMED</span></div>",
        unsafe_allow_html=True,
    )
    st.progress(completed / total)

    for idx, (done, label) in enumerate(checks):
        name = short_names[idx] if idx < len(short_names) else str(label).upper()[:12]
        icon = "DONE" if done else "OPEN"
        with status_cols[idx]:
            st.markdown(
                f"<div style='text-align:center;border:1px solid "
                f"{'#5fcb8a' if done else '#34404d'};border-radius:8px;padding:7px 4px;"
                f"font-size:.72rem;font-weight:900;color:"
                f"{'#5fcb8a' if done else '#8d99a7'}'>{icon} {name}</div>",
                unsafe_allow_html=True,
            )

    missing = list(getattr(state.confirmation, "missing_conditions", None) or [])
    if get_conflict_zone(state):
        blocker = "Price is inside opposing supply/demand structure."
    elif missing:
        blocker = str(missing[0])
    elif completed < len(checks):
        blocker = "The setup is waiting for the next deterministic validation condition."
    else:
        blocker = "All deterministic execution conditions are confirmed."

    if completed == len(checks) and checks:
        st.success(f"READY: {blocker}")
    else:
        st.markdown(
            f"<div style='margin-top:12px;padding:11px 14px;border-left:3px solid #ff4b55;"
            f"background:#111820;border-radius:5px'>"
            f"<span style='font-size:.66rem;font-weight:900;color:#ff4b55;letter-spacing:.08em'>"
            f"CURRENT BLOCKER</span><br>"
            f"<span style='font-size:.86rem;color:#d9e0e7'>{blocker}</span></div>",
            unsafe_allow_html=True,
        )

    if missing:
        next_steps = " -> ".join(str(item) for item in missing[:3])
        st.caption(f"NEXT: {next_steps}")
    elif completed == len(checks) and checks:
        st.caption("NEXT: Preserve the canonical trade plan and monitor execution/risk state.")


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
            f"**Trade Zone:** {execution.get('timeframe', '--')} "
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


def professor_md(text):
    """Render Professor prose without Streamlit treating dollar prices as LaTeX math."""
    return str(text or "").replace("$", r"\$")


def selected_setup_professor_payload(state, setup, lifecycle, plan):
    """Ground Professor follow-up in the exact selected deterministic setup."""
    payload = dict(state.professor_payload() or {})
    payload["selected_setup"] = {
        "candidate_id": str(getattr(setup, "candidate_id", "")),
        "symbol": str(getattr(state, "root_symbol", DISPLAY_SYMBOL)),
        "direction": "LONG" if getattr(setup, "zone_type", "") == "demand" else "SHORT",
        "timeframe": str(getattr(setup, "timeframe", "--")),
        "zone_type": str(getattr(setup, "zone_type", "--")).upper(),
        "zone_low": safe_float(getattr(setup, "lower_bound", None)),
        "zone_high": safe_float(getattr(setup, "upper_bound", None)),
        "setup_score": safe_float(getattr(setup, "setup_score", None)),
        "zone_quality_score": safe_float(getattr(setup, "zone_quality_score", None)),
        "freshness_score": safe_float(getattr(setup, "freshness_score", None)),
        "retests": getattr(setup, "retests", None),
        "projected_rr": safe_float(getattr(setup, "projected_rr", None)),
        "lifecycle": str(getattr(setup, "lifecycle", "--")),
        "execution_stage": str(getattr(lifecycle, "stage", "--")),
        "trade_ready": bool(getattr(lifecycle, "trade_ready", False)),
        "execution_reason": str(getattr(lifecycle, "reason", "")),
        "entry": safe_float(plan.get("entry")),
        "stop": safe_float(plan.get("stop")),
        "target_1": safe_float(plan.get("t1")),
        "target_2": safe_float(plan.get("t2")),
        "risk_dollars_per_contract": safe_float(plan.get("risk_dollars")),
        "target_1_rr": safe_float(plan.get("rr1")),
        "target_2_rr": safe_float(plan.get("rr2")),
    }
    return payload


def setup_professor_assessment(state, setup, lifecycle, plan):
    """Conservative UI assessment derived only from deterministic Trading Pulse state."""
    ready = bool(getattr(lifecycle, "trade_ready", False))
    lifecycle_name = str(getattr(setup, "lifecycle", "") or "").upper()
    stage_name = str(getattr(lifecycle, "stage", "") or "").upper()
    missing = list(getattr(state.confirmation, "missing_conditions", None) or [])
    conflict = bool(get_conflict_zone(state))
    entry = safe_float(plan.get("entry"))
    stop = safe_float(plan.get("stop"))
    risk_points = safe_float(plan.get("risk_points"))

    invalid = (
        lifecycle_name in {"INVALIDATED", "EXPIRED", "BROKEN", "CANCELLED", "CANCELED"}
        or stage_name in {"INVALIDATED", "EXPIRED", "BROKEN", "CANCELLED", "CANCELED"}
        or entry is None or stop is None or risk_points is None or risk_points <= 0
    )
    if ready and not invalid:
        return "TAKE", "The deterministic execution gate is satisfied. Follow the canonical plan; do not alter the engine levels."
    if invalid:
        return "AVOID", "The selected idea is invalid, expired, or lacks a complete deterministic risk plan. Do not treat it as executable."

    reasons = []
    if conflict:
        reasons.append("opposing structure is still in the way")
    if missing:
        reasons.append("confirmation is incomplete")
    if not reasons:
        reasons.append("the execution gate is not yet satisfied")
    return "WATCH", "The structure is worth monitoring, but " + " and ".join(reasons) + ". Wait for Trading Pulse to confirm the trade."


def clean_professor_answer(answer):
    """Keep citations in the grounding expander instead of dumping source metadata into prose."""
    text = str(answer or "").strip()
    if not text:
        return text
    kept = []
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith("futuresprof source context:") or low.startswith("source context:"):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def render_selected_setup_professor(state, setup, lifecycle, plan):
    """Deep, interactive explanation workspace for the selected deterministic setup."""
    side = "LONG" if setup.zone_type == "demand" else "SHORT"
    missing = list(getattr(state.confirmation, "missing_conditions", None) or [])
    conflict = zone_dict(get_conflict_zone(state))
    news_warning, news_level = get_news_state()
    ready = bool(getattr(lifecycle, "trade_ready", False))

    entry = safe_float(plan.get("entry"))
    stop = safe_float(plan.get("stop"))
    t1 = safe_float(plan.get("t1"))
    t2 = safe_float(plan.get("t2"))
    current = safe_float(getattr(state, "current_price", None))
    zone_low = safe_float(getattr(setup, "lower_bound", None))
    zone_high = safe_float(getattr(setup, "upper_bound", None))
    score = safe_float(getattr(setup, "setup_score", None))
    quality = safe_float(getattr(setup, "zone_quality_score", None))
    freshness = safe_float(getattr(setup, "freshness_score", None))
    retests = getattr(setup, "retests", None)
    lifecycle_name = str(getattr(setup, "lifecycle", "--")).replace("_", " ")
    rr1 = safe_float(plan.get("rr1"))
    rr2 = safe_float(plan.get("rr2"))
    risk_points = safe_float(plan.get("risk_points"))
    risk_dollars = safe_float(plan.get("risk_dollars"))

    if ready:
        confirmation_text = "All deterministic execution checks are currently satisfied."
    elif missing:
        confirmation_text = "; ".join(str(x) for x in missing[:4])
    else:
        confirmation_text = str(getattr(lifecycle, "reason", "Waiting for deterministic confirmation."))

    conflict_text = "No opposing canonical conflict zone is currently flagged."
    if conflict:
        conflict_text = (
            f"Opposing {conflict.get('timeframe','--')} {str(conflict.get('type','')).upper()} "
            f"at {money(conflict.get('lower_bound'))} - {money(conflict.get('upper_bound'))}."
        )

    zone_text = (
        f"{money(zone_low)} to {money(zone_high)}"
        if zone_low is not None and zone_high is not None else "the selected canonical zone"
    )
    quality_text = f"{quality/10.0:.1f}/10" if quality is not None else "--"
    fresh_text = f"{freshness/10.0:.1f}/10" if freshness is not None else "--"
    retest_text = str(retests) if retests is not None else "--"

    if side == "LONG":
        entry_logic = (
            f"The engine plans the long at {money(entry)} around the {setup.timeframe} DEMAND structure "
            f"({zone_text}). The idea is to participate only where buyers previously demonstrated control, "
            f"rather than chase price higher. The setup is currently {lifecycle_name}; execution remains governed "
            f"by the confirmation gate shown below."
        )
        stop_logic = (
            f"The stop at {money(stop)} is the deterministic invalidation level below the long thesis. "
            f"A sustained move through that level means the demand structure the setup depends on has failed. "
            f"It is not a Professor-generated number and the Professor will not move it farther away to rescue a trade."
        )
    else:
        entry_logic = (
            f"The engine plans the short at {money(entry)} around the {setup.timeframe} SUPPLY structure "
            f"({zone_text}). The idea is to participate where sellers previously demonstrated control, "
            f"rather than chase price lower. The setup is currently {lifecycle_name}; execution remains governed "
            f"by the confirmation gate shown below."
        )
        stop_logic = (
            f"The stop at {money(stop)} is the deterministic invalidation level above the short thesis. "
            f"A sustained move through that level means the supply structure the setup depends on has failed. "
            f"It is not a Professor-generated number and the Professor will not move it farther away to rescue a trade."
        )

    thesis = (
        f"This is a {score10(score)} {side} candidate built from a {setup.timeframe} "
        f"{setup.zone_type.upper()} zone. Zone quality is {quality_text}, freshness is {fresh_text}, "
        f"and recorded retests are {retest_text}. The setup is interesting because the canonical candidate engine "
        f"has identified actionable structure, but a good zone is not automatically an executable trade. "
        f"The lifecycle, confirmation state, opposing structure, risk/reward and event context still have to agree."
    )

    target_logic = (
        f"Target 1 is {money(t1)}"
        + (f" ({rr1:.2f}R)" if rr1 is not None else "")
        + f" and Target 2 is {money(t2)}"
        + (f" ({rr2:.2f}R)" if rr2 is not None else "")
        + ". These are the deterministic plan targets currently supplied by Trading Pulse. "
          "The Professor explains how to monitor the path to them; it does not silently substitute new targets."
    )

    if current is not None and entry is not None:
        distance = abs(current - entry)
        location_text = f"Current canonical price is {money(current)}, {distance:,.2f} points from planned entry."
    else:
        location_text = "Current-price distance is unavailable in this snapshot."

    assessment, assessment_reason = setup_professor_assessment(state, setup, lifecycle, plan)
    assessment_color = {"TAKE": "#35c76f", "WATCH": "#7ea6d8", "AVOID": "#ff4d57"}.get(assessment, "#7ea6d8")
    symbol = str(getattr(state, "root_symbol", None) or DISPLAY_SYMBOL)
    st.markdown(
        f"<div style='border:1px solid {assessment_color};border-left:5px solid {assessment_color};"
        f"background:#0d131b;border-radius:9px;padding:14px 16px;margin:4px 0 16px'>"
        f"<div style='font-size:.66rem;font-weight:900;letter-spacing:.14em;color:#9fa9b7'>"
        f"PROFESSOR ASSESSMENT · {symbol} · {setup.timeframe}</div>"
        f"<div style='font-size:1.55rem;font-weight:950;color:{assessment_color};margin-top:3px'>{assessment}</div>"
        f"<div style='font-size:.82rem;color:#d9e0e7;margin-top:5px'>{assessment_reason}</div></div>",
        unsafe_allow_html=True,
    )

    st.markdown("### PROFESSOR TRADE BRIEF")
    st.caption(
        "A live teaching layer grounded in the selected canonical setup. Trading Pulse owns the numbers; "
        "the Professor explains the thesis, evidence, confirmation, management and risks."
    )

    st.markdown("#### TRADE THESIS")
    st.markdown(professor_md(thesis))
    st.caption(location_text)

    left, right = st.columns(2, gap="medium")
    with left:
        st.markdown("#### WHY THIS ENTRY")
        st.markdown(professor_md(entry_logic))
    with right:
        st.markdown("#### WHY THIS STOP")
        st.markdown(professor_md(stop_logic))

    st.markdown("#### TARGETS & TRADE-MANAGEMENT ROADMAP")
    st.markdown(professor_md(target_logic))

    r1, r2, r3, r4 = st.columns(4, gap="small")
    r1.markdown(
        f"**1 · BEFORE ENTRY**  \n"
        f"{'Execution gate is satisfied.' if ready else 'WAIT. Confirmation is incomplete.'}  \n\n"
        f"{confirmation_text}"
    )
    r2.markdown(
        f"**2 · AFTER ENTRY**  \n"
        f"Watch whether the selected {setup.timeframe} {setup.zone_type.upper()} structure continues to hold. "
        f"The hard thesis boundary remains {money(stop)}."
    )
    r3.markdown(
        f"**3 · APPROACHING T1**  \n"
        f"Track whether price is progressing cleanly toward {money(t1)} or repeatedly losing the structure that justified entry. "
        f"Do not invent a discretionary exit simply because a candle pulls back."
    )
    r4.markdown(
        f"**4 · T1 → T2**  \n"
        f"Re-ground the trade against the newest MarketState before making a management decision. "
        f"V3.4 does not invent a trailing stop or early-close level that the deterministic engine has not defined."
    )

    st.info(
        "PULLBACK RULE: the Professor can explain whether current structure is strengthening or deteriorating, "
        "but V3.4 will not fabricate an early-close price. The authoritative invalidation remains the engine stop "
        "until a deterministic management rule exists. This is a deliberate V3.4 safety boundary."
    )

    a, b, c = st.columns(3, gap="medium")
    a.markdown(f"**CONFIRMATION / CURRENT BLOCKER**  \n{confirmation_text}")
    b.markdown(f"**STRUCTURAL CONFLICT**  \n{conflict_text}")
    c.markdown(
        f"**PLAN RISK**  \n"
        f"{f'{risk_points:,.2f} pts' if risk_points is not None else '--'}"
        f"{f' / {money(risk_dollars)} per contract' if risk_dollars is not None else ''}"
    )

    level = str(news_level or "UNKNOWN").upper()
    if level in {"HIGH", "CRITICAL", "RED"}:
        st.error(f"EVENT / NEWS RISK: {news_warning}")
    elif level in {"MEDIUM", "MODERATE", "AMBER", "YELLOW"}:
        st.warning(f"EVENT / NEWS RISK: {news_warning}")
    else:
        st.info(f"EVENT / NEWS CONTEXT: {news_warning}")

    if professor_research_available():
        st.success("RESEARCH MODE ONLINE · Professor can use OpenAI web research. New research claims enter PENDING review; they are not learned as truth automatically.")
    else:
        st.info("RESEARCH MODE INSTALLED · Add OPENAI_API_KEY to enable live web research. Local FuturesProf grounding remains available.")

    st.markdown("#### ASK THE PROFESSOR ABOUT THIS TRADE")
    st.caption(
        "Ask follow-ups about the setup, confirmation, stop logic, targets, pullbacks, timeframe conflict, "
        "news, or what your taught material says. Each answer is re-grounded in the current selected MarketState."
    )

    qkey = f"setup_prof_q_{setup.candidate_id}"
    question = st.text_area(
        "Your question",
        placeholder=(
            "Examples:\n"
            "• Why is this entry attractive?\n"
            "• What exact confirmation is still missing?\n"
            "• Why is the stop at this level?\n"
            "• Price pulled back — what changed in the thesis?\n"
            "• What should I watch as price approaches Target 1?\n"
            "• What does my taught material say about this setup?"
        ),
        height=125,
        key=qkey,
    )

    ask_col, clear_col, _ = st.columns([1.1, 0.8, 2.1])
    with ask_col:
        ask = st.button(
            "ASK PROFESSOR",
            type="primary",
            width="stretch",
            key=f"setup_prof_ask_{setup.candidate_id}",
        )
    with clear_col:
        clear = st.button(
            "CLEAR CHAT",
            width="stretch",
            key=f"setup_prof_clear_{setup.candidate_id}",
        )

    history_key = f"setup_prof_history_{setup.candidate_id}"
    if history_key not in st.session_state:
        st.session_state[history_key] = []

    if clear:
        st.session_state[history_key] = []
        st.rerun()

    if ask:
        user_question = str(question or "").strip()
        if not user_question:
            st.warning("Type a question in the box above.")
        else:
            live_payload = selected_setup_professor_payload(state, setup, lifecycle, plan)
            live_payload["professor_assessment"] = setup_professor_assessment(state, setup, lifecycle, plan)[0]
            live_payload["conversation_context"] = [
                {"question": item.get("question", ""), "answer": item.get("answer", "")}
                for item in st.session_state[history_key][-4:]
            ]
            selected_symbol = str(live_payload.get("selected_setup", {}).get("symbol") or DISPLAY_SYMBOL)
            assessment, assessment_reason = setup_professor_assessment(state, setup, lifecycle, plan)
            teaching_prompt = (
                f"Answer as the Trading Pulse Professor about {selected_symbol}. The current deterministic assessment is "
                f"{assessment}: {assessment_reason} Deeply explain the selected trade using the supplied canonical "
                "MarketState and selected_setup values as authoritative facts. Give the trader a direct answer first, "
                "then explain why, what is still missing, what would invalidate the thesis, and what to monitor next. "
                "Connect the answer to retrieved FuturesProf knowledge when relevant, but do not append source titles, "
                "domains, a bibliography, or a 'source context' line in the prose; sources are displayed separately. "
                "Never invent or alter entry, stop, targets, probabilities, confirmation status, execution permission, "
                "or an early-exit level. If the deterministic payload does not define a requested management level or "
                "rule, say that clearly. User question: " + user_question
            )
            packet = answer_question(teaching_prompt, live_payload, research_mode=True)
            packet["answer"] = clean_professor_answer(packet.get("answer", ""))
            st.session_state[history_key].append(
                {
                    "question": user_question,
                    "answer": packet.get("answer", ""),
                    "sources": packet.get("sources") or [],
                    "question_id": packet.get("question_id"),
                    "research_status": packet.get("research_status"),
                    "pending_claims": packet.get("pending_claims", 0),
                }
            )

    history = st.session_state.get(history_key, [])
    if history:
        st.markdown("#### PROFESSOR CONVERSATION")
        for idx, item in enumerate(history[-6:], start=max(1, len(history)-5)):
            st.markdown(f"**YOU · {idx}**  \n{item.get('question','')}")
            st.markdown(professor_md(f"**PROFESSOR**  \n{item.get('answer','')}"))
            sources = item.get("sources") or []
            if sources:
                with st.expander(f"GROUNDING SOURCES · ANSWER {idx}", expanded=False):
                    for source in sources:
                        label = source.get("title") or source.get("domain") or "FuturesProf source"
                        st.write(f"- {label} | {source.get('domain','')} | {source.get('source_type','GROUNDED')}")
            qid = item.get("question_id")
            if qid:
                fb1, fb2, fb3 = st.columns([.7,.7,3])
                if fb1.button("USEFUL", key=f"prof_up_{qid}"):
                    rate_professor_answer(int(qid), 1, None)
                    st.toast("Professor feedback saved")
                if fb2.button("WRONG", key=f"prof_down_{qid}"):
                    rate_professor_answer(int(qid), -1, None)
                    st.toast("Flagged for review")
                fb3.caption(f"Research: {item.get('research_status','--')} · Pending claims: {item.get('pending_claims',0)}")
            st.divider()

    with st.expander("PROFESSOR GROUNDING / ADVANCED DETAILS", expanded=False):
        st.markdown(
            "**LIVE TRADING PULSE FACTS** — selected MarketState, candidate, lifecycle, confirmation, "
            "entry/stop/targets and current event state."
        )
        st.markdown(
            "**TAUGHT + GROUNDED KNOWLEDGE** — FuturesProf retrieval used by Professor answers when relevant."
        )
        st.markdown(
            "**HISTORICAL EVIDENCE** — used only when the available evidence layer supplies it; no fake probability."
        )
        st.json(selected_setup_professor_payload(state, setup, lifecycle, plan), expanded=False)


# ---------------------------------------------------------------------
# SESSION / MARKETSTATE
# ---------------------------------------------------------------------

if "active_symbol" not in st.session_state:
    st.session_state.active_symbol = "GC"
active_symbol = str(st.session_state.active_symbol).upper()
active_instrument = get_instrument(active_symbol)
DISPLAY_SYMBOL = active_symbol
MARKET_NAME = active_instrument.name.upper()
COACH_NAME = f"{active_instrument.name.upper()} COACH"

if "chart_tf" not in st.session_state:
    st.session_state.chart_tf = DEFAULT_CHART_TF

if "zone_quality" not in st.session_state:
    st.session_state.zone_quality = "B"
for _key, _default in {
    "layer_context": False,
    "layer_execution": False,
    "layer_conflict": False,
    "layer_htf_supply": False,
    "layer_ltf_supply": False,
    "layer_htf_demand": False,
    "layer_ltf_demand": False,
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

with st.spinner(f"Building canonical {active_symbol} MarketState..."):
    try:
        market_state = get_market_state(active_symbol)
    except Exception as exc:
        st.error(f"Unable to build MarketState: {exc}")
        st.stop()

# V3.4 Pass 2B: one canonical candidate calculation per Streamlit rerun.
# Every dashboard consumer below reuses this immutable rerun snapshot.
canonical_candidates = build_setup_candidates(market_state)

health, age_minutes = data_health(market_state.market_timestamp)
news_warning, news_level = get_news_state()
data_truth = truth_status()
try:
    market_watch_snapshot = get_market_watch()
except Exception:
    market_watch_snapshot = {}
_watch_price = safe_float((market_watch_snapshot.get(active_symbol) or {}).get("price"))
_state_price = safe_float(market_state.current_price)
market_data_integrity_ok = True
if _watch_price is not None and _state_price is not None:
    _active_tick = max(float(get_instrument(active_symbol).tick_size), 1e-12)
    market_data_integrity_ok = abs(_watch_price - _state_price) / _active_tick <= 1.01


# ---------------------------------------------------------------------
# HEADER - BRANDED PRODUCTION BAR
# ---------------------------------------------------------------------

header_logo, header_title = st.columns([1.35, 5.65], gap="medium")
with header_logo:
    if BRAND_LOGO.exists():
        st.image(str(BRAND_LOGO), width="stretch")
    else:
        st.markdown(f"<div style='color:#ff4b55;font-weight:900'>{APP_NAME}</div>", unsafe_allow_html=True)

with header_title:
    st.markdown(
        f"""<div class="tp-hero-card">
        <div class="tp-hero-kicker">AI ASSISTED FUTURES TRADING</div>
        <div class="tp-hero-title">{COACH_NAME}</div>
        <div class="tp-hero-tagline">Stop Chasing Trades. Let the Market Come to You.</div>
        <div class="tp-hero-sub">SUPPLY | DEMAND | STRUCTURE | EXECUTION</div>
        </div>""",
        unsafe_allow_html=True,
    )

command_tabs = ["COMMAND CENTER", "JOURNAL", "BACKTEST", "PROFESSOR"]
dashboard_tab, journal_tab, backtest_tab, professor_tab = st.tabs(command_tabs)

with dashboard_tab:
    st.warning(
        f"DATA STATUS - Market: {data_truth.market_source} (delayed / not execution eligible). "
        f"Evidence: {data_truth.evidence_source or 'not installed'}. {data_truth.warning}"
    )
    # V3.4 Pass 3A: global multi-market / multi-timeframe Elite board.
    # The selected chart does not control opportunity discovery.
    # This is presentation only: no journal writes occur during Streamlit rendering.
    with st.spinner("Scanning all markets for Elite opportunities..."):
        global_elite, elite_diagnostics = get_global_elite_snapshot()

    st.markdown("""
    <style>
    .tp-elite-wrap {border:1px solid #26364b;border-radius:10px;padding:14px 16px 16px;background:linear-gradient(180deg,#0c131d 0%,#080d14 100%);margin:8px 0 12px;}
    .tp-elite-head {display:flex;align-items:end;justify-content:space-between;margin-bottom:4px;}
    .tp-elite-title {font-size:18px;font-weight:900;color:#f7f8fb;letter-spacing:.02em;}
    .tp-elite-sub {font-size:11px;color:#8192aa;margin-top:2px;}
    .tp-elite-count {font-size:11px;font-weight:900;color:#ff6b74;letter-spacing:.08em;}
    .tp-opp-card {border:1px solid #52657a;border-radius:10px;background:#0b1620;overflow:hidden;min-height:196px;box-shadow:0 8px 20px rgba(0,0,0,.18);}
    .tp-opp-top {display:grid;grid-template-columns:.85fr 1.3fr .85fr;border-bottom:1px solid #52657a;align-items:center;}
    .tp-opp-top span {padding:8px 9px;font-weight:900;font-size:11px;border-right:1px solid #52657a;line-height:1.1;}
    .tp-opp-top span:nth-child(1) {text-align:left;letter-spacing:.04em;}
    .tp-opp-top span:nth-child(2) {text-align:center;font-size:17px;letter-spacing:.08em;color:#ffffff;text-shadow:0 0 10px rgba(255,255,255,.06);}
    .tp-opp-top span:nth-child(3) {border-right:0;text-align:center;font-size:18px;padding-top:5px;padding-bottom:5px;}
    .tp-long {color:#43dc8b}.tp-short {color:#ff5b57}.tp-up{color:#43dc8b}.tp-down{color:#ff5b57}
    .tp-opp-row {display:grid;grid-template-columns:1fr 1.45fr;border-bottom:1px solid #52657a;}
    .tp-opp-row:last-child {border-bottom:0;}
    .tp-opp-row span {padding:7px 9px;font-size:12px;border-right:1px solid #52657a;}
    .tp-opp-row span:last-child {border-right:0;text-align:right;font-weight:800;color:#f5f7fa;}
    .tp-opp-label {font-weight:800;color:#d8e0e9;}
    .tp-opp-meta {padding:7px 9px;color:#ff6b74;font-size:10px;font-weight:800;letter-spacing:.03em;}
    </style>
    """, unsafe_allow_html=True)

    # V3.4 Final: always show one best available setup per enabled market.
    # Elite remains a strict 9.0+ global designation and receives a star.
    # The board is useful even when only zero or one market is currently Elite.
    elite_by_symbol = {opportunity.symbol: opportunity for opportunity in global_elite}
    best_setups = []

    for scan_symbol in MARKET_WATCH_ORDER:
        try:
            scan_state = get_market_state(scan_symbol)
            scan_candidates = build_setup_candidates(scan_state)
            if not scan_candidates:
                continue

            graded_candidates = [
                (candidate, grade_live_candidate(candidate, scan_state, scan_symbol))
                for candidate in scan_candidates
            ]
            promoted_candidates = [pair for pair in graded_candidates if pair[1]["tier"] == "V4 ELITE"]
            elite_opportunity = elite_by_symbol.get(scan_symbol)
            if promoted_candidates:
                best_candidate, v4_grade = max(
                    promoted_candidates,
                    key=lambda pair: (
                        safe_float(pair[1].get("confidence10"), 0.0) or 0.0,
                        safe_float(getattr(pair[0], "setup_score", None), 0.0) or 0.0,
                    ),
                )
                composite_score = safe_float(getattr(best_candidate, "setup_score", None), 0.0) or 0.0
                confirmation_count = 0
                mtf_aligned = 0
                mtf_total = 0
                direction = "LONG" if str(best_candidate.zone_type).lower() == "demand" else "SHORT"
            elif elite_opportunity is not None:
                best_candidate = elite_opportunity.candidate
                composite_score = safe_float(elite_opportunity.composite_score, 0.0) or 0.0
                confirmation_count = elite_opportunity.confirmation_count
                mtf_aligned = elite_opportunity.mtf_aligned
                mtf_total = elite_opportunity.mtf_total
                direction = elite_opportunity.direction
            else:
                best_candidate = max(
                    scan_candidates,
                    key=lambda c: (
                        safe_float(getattr(c, "setup_score", None), 0.0) or 0.0,
                        safe_float(getattr(c, "zone_quality_score", None), 0.0) or 0.0,
                        safe_float(getattr(c, "projected_rr", None), 0.0) or 0.0,
                    ),
                )
                composite_score = safe_float(getattr(best_candidate, "setup_score", None), 0.0) or 0.0
                confirmation_count = 0
                mtf_aligned = 0
                mtf_total = 0
                direction = "LONG" if str(best_candidate.zone_type).lower() == "demand" else "SHORT"
            if not promoted_candidates:
                v4_grade = grade_live_candidate(best_candidate, scan_state, scan_symbol)
            is_elite = has_live_star(v4_grade)

            best_setups.append({
                "symbol": scan_symbol,
                "state": scan_state,
                "candidate": best_candidate,
                "composite_score": composite_score,
                "confirmation_count": confirmation_count,
                "mtf_aligned": mtf_aligned,
                "mtf_total": mtf_total,
                "direction": direction,
                "is_elite": is_elite,
                "v4_grade": v4_grade,
            })
        except Exception:
            continue

    st.markdown(
        f"""<div class="tp-elite-wrap"><div class="tp-elite-head"><div>
        <div class="tp-elite-title">BEST TRADE SETUPS</div>
        <div class="tp-elite-sub">A star requires A+ structure, promoted evidence, and verified first-touch execution. Evidence matches remain unstarred until stop/target ordering is proven.</div>
        </div><div class="tp-elite-count">{sum(1 for item in best_setups if item['is_elite'])} V4 ELITE &#9733;</div></div></div>""",
        unsafe_allow_html=True,
    )

    if best_setups:
        setup_cols = st.columns(4, gap="medium")
        for i, item in enumerate(best_setups):
            candidate = item["candidate"]
            setup_state = item["state"]
            side = item["direction"]
            arrow = "&#8593;" if side == "LONG" else "&#8595;"
            side_cls = "tp-long" if side == "LONG" else "tp-short"
            arrow_cls = "tp-up" if side == "LONG" else "tp-down"
            elite_star = " &#9733;" if item["is_elite"] else ""
            v4_grade = item["v4_grade"]
            elite_label = v4_grade["tier"]
            confidence = v4_grade.get("confidence10")
            confidence_text = "--" if confidence is None else f"{confidence:.1f}/10"
            sample_count = int(v4_grade.get('sample') or 0)
            sample_text = f"{sample_count} triggered" if data_truth.live_promotion and sample_count else "--"

            try:
                setup_plan = planned_trade_metrics(candidate, setup_state) if market_data_integrity_ok else {}
            except Exception:
                setup_plan = {}

            mtf_text = (
                f"{item['mtf_aligned']}/{item['mtf_total']} aligned"
                if item["mtf_total"] else "best current candidate"
            )

            with setup_cols[i % len(setup_cols)]:
                st.markdown(
                    f"""<div class="tp-opp-card">
                      <div class="tp-opp-top"><span class="{side_cls}">{side}</span><span>{item['symbol']}{elite_star}</span><span class="{arrow_cls}">{arrow}</span></div>
                      <div class="tp-opp-row"><span class="tp-opp-label">Status</span><span>{elite_label}</span></div>
                      <div class="tp-opp-row"><span class="tp-opp-label">Structure Score</span><span>{score10(candidate.setup_score)}</span></div>
                      <div class="tp-opp-row"><span class="tp-opp-label">Evidence Confidence</span><span>{confidence_text if data_truth.live_promotion else '--'}</span></div>
                      <div class="tp-opp-row"><span class="tp-opp-label">Comparable Sample</span><span>{sample_text}</span></div>
                      <div class="tp-opp-row"><span class="tp-opp-label">Execution Validation</span><span>{v4_grade.get('execution_status', 'NOT QUALIFIED')}</span></div>
                      <div class="tp-opp-row"><span class="tp-opp-label">Timeframe</span><span>{candidate.timeframe} {candidate.zone_type.upper()}</span></div>
                      <div class="tp-opp-row"><span class="tp-opp-label">MTF Context</span><span>{mtf_text}</span></div>
                      <div class="tp-opp-row"><span class="tp-opp-label">Entry</span><span>{money(setup_plan.get('entry'))}</span></div>
                      <div class="tp-opp-row"><span class="tp-opp-label">Stop</span><span>{money(setup_plan.get('stop'))}</span></div>
                      <div class="tp-opp-row"><span class="tp-opp-label">Target 1</span><span>{money(setup_plan.get('t1'))}</span></div>
                      <div class="tp-opp-row"><span class="tp-opp-label">Target 2</span><span>{money(setup_plan.get('t2'))}</span></div>
                      <div class="tp-opp-meta">{candidate.lifecycle.replace('_',' ')} / {candidate.distance_points:.2f} pts from zone</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
                if st.button(
                    "LOAD THIS SETUP",
                    key=f"best_load_{item['symbol']}_{candidate.candidate_id}",
                    width="stretch",
                ):
                    tf_display = {"D": "1D", "W": "1W"}.get(candidate.timeframe, candidate.timeframe)
                    st.session_state.active_symbol = item["symbol"]
                    if tf_display in CHART_TIMEFRAMES:
                        st.session_state.chart_tf = tf_display
                    st.session_state.focused_candidate_id = candidate.candidate_id
                    st.session_state[f"preferred_candidate_{tf_display}"] = candidate.candidate_id
                    st.rerun()
    else:
        st.caption("No canonical setup candidates are currently available across the enabled markets.")

    # Only promoted V4 Elite setups may be journaled automatically for paper tracking.
    for item in best_setups:
        if not item["is_elite"]:
            continue
        try:
            elite_plan = planned_trade_metrics(item["candidate"], item["state"])
            add_candidate_to_journal(
                item["candidate"],
                elite_plan,
                engine_version="4.0-promoted-elite",
                source="V4_ELITE_AUTO",
            )
        except Exception:
            pass

    # Cross-market watch strip. GC is the active full-analysis market.
    market_watch = market_watch_snapshot

    # V3.3G canonical-source integrity guard. Market Watch must agree with the
    # same MarketState price boundary used by the chart/analysis pipeline.
    _watch_active = safe_float((market_watch.get(active_symbol) or {}).get("price"))
    _state_active = safe_float(market_state.current_price)
    if _watch_active is not None and _state_active is not None:
        _tick = max(float(get_instrument(active_symbol).tick_size), 1e-12)
        _delta_ticks = abs(_watch_active - _state_active) / _tick
        if not market_data_integrity_ok:
            st.error(f"DATA INTEGRITY BLOCK: {active_symbol} Market Watch ({_watch_active:,.2f}) != reference MarketState ({_state_active:,.2f}). Exact trade levels and chart overlays are hidden until the feeds agree.")
    render_market_watch(market_watch)
    _switch_cols = st.columns(len(MARKET_WATCH_ORDER))
    for _i, _symbol in enumerate(MARKET_WATCH_ORDER):
        if _switch_cols[_i].button(_symbol, key=f"switch_market_{_symbol}", width="stretch", type="primary" if _symbol == active_symbol else "secondary"):
            if _symbol != active_symbol:
                st.session_state.active_symbol = _symbol
                st.session_state.focused_candidate_id = None
                st.rerun()

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

    st.caption("Multi-timeframe alignment is context only; Trade Ready still requires confirmation and risk validation.")

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
            width="stretch",
            type=button_type,
            key=f"tf_{display_tf}",
        ):
            st.session_state.chart_tf = display_tf
            st.session_state.focused_candidate_id = None
            st.session_state.pop("focused_setup_selector", None)
            st.rerun()

    selected_tf = st.session_state.chart_tf

    # Legacy foundation: fixed-height decision strip directly between timeframe selection and chart.
    # News is intentionally bounded so a busy calendar never pushes the chart down.
    news_col, toolkit_col = st.columns([1.0, 1.45], gap="medium")
    with news_col:
        news_color = "red" if news_level == "HIGH" else "green" if news_level == "LOW" else ""
        st.markdown(f"""<div class="tp-intel-card" style="margin:4px 0 0;height:157px;max-height:157px;overflow-y:auto;overflow-x:hidden">
          <div class="tp-intel-title {news_color}">NEWS IMPACT</div>
          <div class="tp-intel-value">{news_level}</div>
          <div class="tp-intel-detail">{news_warning}</div></div>""", unsafe_allow_html=True)

    with toolkit_col:
        st.markdown("<div style='text-align:center;font-weight:800;letter-spacing:.04em;margin-bottom:8px'>TRADER TOOLKIT</div>", unsafe_allow_html=True)

        def _toolkit_toggle(label: str, state_key: str, button_key: str):
            active = bool(st.session_state.get(state_key, False))
            if st.button(label, width="stretch", type="primary" if active else "secondary", key=button_key):
                st.session_state[state_key] = not active
                st.rerun()

        # Setup-quality controls are independent grade-family toggles. ALL is a
        # one-click select-all action; selecting/deselecting individual families
        # never forces the others to change.
        st.markdown("<div style='text-align:center;color:#7f8998;font-size:.78rem;font-weight:700;margin:2px 0 6px'>SETUP QUALITY</div>", unsafe_allow_html=True)
        quality_cols = st.columns(5, gap="small")
        quality_controls = [
            ("ELITE 9.2+", "zone_grade_aplus"),
            ("STRONG 8.2+", "zone_grade_a"),
            ("DEVELOPING 7.0+", "zone_grade_b"),
            ("LEARNING 5.5+", "zone_grade_c"),
        ]
        for idx, (label, state_key) in enumerate(quality_controls):
            active = bool(st.session_state.get(state_key, False))
            if quality_cols[idx].button(label, width="stretch", type="primary" if active else "secondary", key=f"quality_toggle_{state_key}"):
                st.session_state[state_key] = not active
                st.rerun()

        all_quality_selected = all(bool(st.session_state.get(key, False)) for _, key in quality_controls)
        if quality_cols[4].button("ALL", width="stretch", type="primary" if all_quality_selected else "secondary", key="quality_toggle_all"):
            for _, state_key in quality_controls:
                st.session_state[state_key] = True
            st.rerun()

        # Derive the legacy minimum-grade boundary from the lowest independently
        # enabled family. enabled_grades below remains the authoritative switch map.
        if st.session_state.zone_grade_c:
            st.session_state.zone_quality = "C"
        elif st.session_state.zone_grade_b:
            st.session_state.zone_quality = "B"
        elif st.session_state.zone_grade_a:
            st.session_state.zone_quality = "A"
        else:
            st.session_state.zone_quality = "A+"

        zone_group, layer_group = st.columns(2, gap="medium")
        with zone_group:
            st.markdown("<div style='text-align:center;color:#7f8998;font-size:.78rem;font-weight:700;margin:2px 0 6px'>ZONES</div>", unsafe_allow_html=True)
            zone_cols = st.columns(4, gap="small")
            zone_controls = [
                ("HTF SUPPLY", "layer_htf_supply"),
                ("LTF SUPPLY", "layer_ltf_supply"),
                ("HTF DEMAND", "layer_htf_demand"),
                ("LTF DEMAND", "layer_ltf_demand"),
            ]
            for idx, (label, state_key) in enumerate(zone_controls):
                with zone_cols[idx]:
                    _toolkit_toggle(label, state_key, f"zone_toggle_{state_key}")

        with layer_group:
            st.markdown("<div style='text-align:center;color:#7f8998;font-size:.78rem;font-weight:700;margin:2px 0 6px'>CHART LAYERS</div>", unsafe_allow_html=True)
            layer_cols = st.columns(5, gap="small")
            layer_controls = [
                ("SMA 20", "layer_sma20"),
                ("SMA 50", "layer_sma50"),
                ("EMA 21", "layer_ema21"),
                ("VWAP", "layer_vwap"),
                ("VOLUME", "layer_volume"),
            ]
            for idx, (label, state_key) in enumerate(layer_controls):
                with layer_cols[idx]:
                    _toolkit_toggle(label, state_key, f"chart_toggle_{state_key}")

        st.session_state.layer_sma200 = False
        st.session_state.layer_ema9 = False
        st.caption("Display controls only. Trading Pulse analysis remains synchronized across the dashboard.")

    # Load active timeframe data once; OHLC metrics render directly above the chart.
    try:
        chart_df = get_chart_data(selected_tf, 260, active_symbol)
    except Exception:
        chart_df = None

    # V2.10D: the active chart, opportunity panel and trade setup panel all use
    # the SAME active-timeframe candidate set.
    enabled_29a = {
        "A+": st.session_state.zone_grade_aplus,
        "A": st.session_state.zone_grade_a,
        "B": st.session_state.zone_grade_b,
        "C": st.session_state.zone_grade_c,
        "D": False,
    }
    candidate_tf = {"1D": "D", "1W": "W"}.get(selected_tf, selected_tf)
    visible_29a = filter_candidates(
        canonical_candidates,
        minimum_grade=st.session_state.zone_quality,
        enabled_grades=enabled_29a,
        relevant_timeframes={candidate_tf},
        limit=12,
    )

    # Resolve the selected setup BEFORE chart rendering. This makes setup
    # buttons persistent across reruns and drives the chart overlay correctly.
    focused_candidate = None
    selected_key = f"selected_setup_{selected_tf}"
    if visible_29a:
        selected_index = int(st.session_state.get(selected_key, 0) or 0)
        selected_index = min(max(selected_index, 0), len(visible_29a) - 1)
        focused_candidate = visible_29a[selected_index]
        st.session_state.focused_candidate_id = focused_candidate.candidate_id
    else:
        st.session_state.focused_candidate_id = None

    # Primary visual gets the full page width.
    chart_col = st.container()

    with chart_col:
        chart_price = safe_float(chart_df["close"].iloc[-1]) if chart_df is not None and len(chart_df) else safe_float(market_state.current_price)
        st.markdown(
            f'<div class="tp-chart-head" style="display:flex;justify-content:space-between;align-items:end">'
            f'<span>{DISPLAY_SYMBOL} / {MARKET_NAME} &nbsp;&bull;&nbsp; TIMEFRAME <b>{selected_tf}</b></span>'
            f'<span style="font-size:1.20rem">LAST {money(chart_price)}</span></div>',
            unsafe_allow_html=True)
        if chart_df is not None and len(chart_df) >= 1:
            last_candle = chart_df.iloc[-1]
            o1,o2,o3,o4 = st.columns(4)
            o1.metric("OPEN", money(last_candle["open"]))
            o2.metric("HIGH", money(last_candle["high"]))
            o3.metric("LOW", money(last_candle["low"]))
            o4.metric("CLOSE", money(last_candle["close"]))

        try:
            if chart_df is not None and len(chart_df) >= 5:
                chart = build_candlestick_chart(
                    chart_df, selected_tf, market_state,
                    min_zone_grade=st.session_state.zone_quality,
                    show_context=st.session_state.layer_context,
                    show_execution=st.session_state.layer_execution,
                    show_conflict=st.session_state.layer_conflict,
                    focused_candidate_id=st.session_state.get("focused_candidate_id") if market_data_integrity_ok else None,
                    candidates=canonical_candidates if market_data_integrity_ok else [],
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
                rendered_tv = render_tradingview_lightweight_chart(
                    chart_df, selected_tf, market_state,
                    focused_candidate_id=st.session_state.get("focused_candidate_id") if market_data_integrity_ok else None,
                    candidates=canonical_candidates if market_data_integrity_ok else [],
                    show_context=st.session_state.layer_context,
                    show_execution=st.session_state.layer_execution,
                    show_conflict=st.session_state.layer_conflict,
                    show_sma20=st.session_state.layer_sma20,
                    show_sma50=st.session_state.layer_sma50,
                    show_sma200=st.session_state.layer_sma200,
                    show_ema9=st.session_state.layer_ema9,
                    show_ema21=st.session_state.layer_ema21,
                    show_vwap=st.session_state.layer_vwap,
                    show_volume=st.session_state.layer_volume,
                )
                if not rendered_tv and chart is not None:
                    st.altair_chart(chart, width="stretch")

                note = f"{len(chart_df):,} candles / TradingView Lightweight Charts / Minimum potential grade {st.session_state.zone_quality}"
                if selected_tf == "30m":
                    note += " / 30m resampled from 15m"
                st.markdown(f'<div class="tp-footnote">{note} / Trading Pulse analysis remains synchronized across the dashboard.</div>',
                            unsafe_allow_html=True)
            else:
                st.warning(f"Not enough {selected_tf} data.")
        except Exception as exc:
            st.error(f"Chart error: {exc}")

        st.markdown('<div class="tp-section-rule"></div>', unsafe_allow_html=True)

        # Legacy foundation: the old quick setup buttons were redundant with the canonical selector below.
        if visible_29a:
            setup_labels = [
                (
                    f"{score10(c.setup_score)}  |  "
                    f"{'LONG' if c.zone_type == 'demand' else 'SHORT'}  |  "
                    f"{c.timeframe} {c.zone_type.upper()}  |  "
                    f"{money(c.lower_bound)} - {money(c.upper_bound)}  |  "
                    f"{c.lifecycle.replace('_', ' ')}"
                )
                for c in visible_29a
            ]
            selected_key = f"selected_setup_{selected_tf}"
            preferred_id = st.session_state.pop(f"preferred_candidate_{selected_tf}", None)
            if preferred_id is not None:
                for _idx, _candidate in enumerate(visible_29a):
                    if _candidate.candidate_id == preferred_id:
                        st.session_state[selected_key] = _idx
                        break
            selected_default = int(st.session_state.get(selected_key, 0) or 0)
            selected_default = min(max(selected_default, 0), len(visible_29a) - 1)

            # Legacy foundation: direct setup buttons replace the redundant dropdown.
            # Presentation/navigation only; canonical candidates remain unchanged.
            st.markdown(
                f"<div style='color:#9aa6b5;font-size:.68rem;font-weight:800;"
                f"letter-spacing:.08em;margin:0 0 6px 0'>{selected_tf.upper()} SUPPLY/DEMAND SETUPS</div>",
                unsafe_allow_html=True,
            )
            button_columns = st.columns(min(len(visible_29a), 4))
            selected_setup_index = selected_default
            for _idx, _candidate in enumerate(visible_29a):
                _side = "LONG" if _candidate.zone_type == "demand" else "SHORT"
                _label = (
                    f"{score10(_candidate.setup_score)} | {_side} | "
                    f"{_candidate.timeframe} {_candidate.zone_type.upper()} | "
                    f"{_candidate.lifecycle.replace('_', ' ')}"
                )
                with button_columns[_idx % len(button_columns)]:
                    if st.button(
                        _label,
                        type="primary" if _idx == selected_default else "secondary",
                        width="stretch",
                        key=f"setup_button_{selected_tf}_{_candidate.candidate_id}",
                    ):
                        st.session_state[selected_key] = _idx
                        st.session_state.focused_candidate_id = _candidate.candidate_id
                        st.rerun()

            setup = visible_29a[selected_setup_index]
            lifecycle = build_execution_lifecycle(market_state, setup)
            plan = planned_trade_metrics(setup, market_state) if market_data_integrity_ok else {}
            title_col, journal_col, spacer_col = st.columns([1.0, 0.72, 1.35])
            with title_col:
                st.markdown("### TRADE SETUP")
            with journal_col:
                if st.button("ADD TO JOURNAL", type="primary", width="stretch", key=f"journal_add_{setup.candidate_id}", disabled=not market_data_integrity_ok):
                    try:
                        trade_id, created = add_candidate_to_journal(setup, plan, engine_version="3.4", source="LIVE_PAPER")
                        if created:
                            st.success(f"Trade #{trade_id} added. Tracking begins from this snapshot.")
                        else:
                            st.info(f"Trade #{trade_id} is already being tracked.")
                    except Exception as exc:
                        st.error(f"Could not add setup to journal: {exc}")
            side = "LONG" if setup.zone_type == "demand" else "SHORT"
            status = lifecycle.stage.replace("_", " ")
            st.markdown(
                f"**{side} {DISPLAY_SYMBOL}  |  {score10(setup.setup_score)} SETUP  |  {setup.timeframe} {setup.zone_type.upper()}  |  {status}**"
            )
            st.caption(
                "Planned trade levels for the selected opportunity. They are informational until the canonical execution lifecycle reaches TRADE READY."
            )
            a,b,c,d = st.columns(4)
            a.metric("ENTRY", money(plan.get("entry")))
            b.metric("STOP LOSS", money(plan.get("stop")))
            c.metric("TARGET 1", money(plan.get("t1")))
            d.metric("TARGET 2", money(plan.get("t2")))
            e,f,g,h = st.columns(4)
            e.metric("RISK / CONTRACT", money(plan.get("risk_dollars")))
            f.metric("T1 R:R", f"1 : {plan['rr1']:.2f}" if plan.get("rr1") is not None else "--")
            g.metric("T1 RETURN / CONTRACT", money(plan.get("return1")))
            h.metric("T2 R:R", f"1 : {plan['rr2']:.2f}" if plan.get("rr2") is not None else "--")
            if plan.get("return2") is not None:
                st.caption(
                    f"Target 2 potential return: {money(plan['return2'])} per GC contract  |  "
                    f"Risk: {plan.get('risk_points', 0):.2f} points / {money(plan.get('risk_dollars'))} per contract  |  "
                    f"Setup score: {score10(setup.setup_score)}  |  Zone quality: {setup.zone_quality_score / 10.0:.1f}/10."
                )
            st.caption("Paper tracking only. Original entry / stop / targets / grade are frozen when added.")
            if lifecycle.trade_ready:
                st.success("TRADE READY - confirmation and risk checks are satisfied.")
            else:
                st.warning(f"PLANNED / NOT EXECUTABLE - {lifecycle.reason}")

            st.markdown('<div class="tp-section-rule"></div>', unsafe_allow_html=True)
            render_selected_setup_professor(market_state, setup, lifecycle, plan)
        else:
            st.markdown("### TRADE SETUP")
            st.info(f"No {selected_tf} trade setup survives the current quality and visibility filters.")

    # PROFESSOR TRADE BRIEF MOVED TO COMMAND CENTER - V3.4
    # Full-width Professor intelligence workspace. Widgets remain visible even
    # before their verified V5 backends are promoted; unavailable values stay blank.
    st.write("")
    watch_opportunities = elite_diagnostics.get("watch_opportunities", [])
    brief_opportunity = watch_opportunities[0] if watch_opportunities else None
    brief_candidate = focused_candidate
    brief_state = market_state
    brief_symbol = active_symbol
    brief_side = (
        "LONG" if brief_candidate and str(brief_candidate.zone_type).lower() == "demand" else "SHORT"
    )
    brief_status = "WATCH" if brief_opportunity else "RESEARCH PREVIEW"
    try:
        brief_plan = planned_trade_metrics(brief_candidate, brief_state) if brief_candidate and market_data_integrity_ok else {}
    except Exception:
        brief_plan = {}

    def _brief_value(value, formatter=None):
        if value is None:
            return "--"
        return formatter(value) if formatter else str(value)

    brief_score = safe_float(getattr(brief_candidate, "setup_score", None)) if brief_candidate else None
    brief_quality = safe_float(getattr(brief_candidate, "zone_quality_score", None)) if brief_candidate else None
    brief_fresh = safe_float(getattr(brief_candidate, "freshness_score", None)) if brief_candidate else None
    brief_rr = safe_float(getattr(brief_candidate, "projected_rr", None)) if brief_candidate else None
    brief_tf = str(getattr(brief_candidate, "timeframe", "--")) if brief_candidate else "--"
    brief_zone_type = str(getattr(brief_candidate, "zone_type", "--")).upper() if brief_candidate else "--"
    brief_lifecycle = str(getattr(brief_candidate, "lifecycle", "WAITING")).replace("_", " ") if brief_candidate else "WAITING"
    brief_mtf = (
        f"{brief_opportunity.mtf_aligned}/{brief_opportunity.mtf_total}"
        if brief_opportunity and brief_opportunity.mtf_total else "--"
    )
    brief_direction_class = "tp-pw-long" if brief_side == "LONG" else "tp-pw-short"
    brief_entry = money(brief_plan.get("entry"))
    brief_stop = money(brief_plan.get("stop"))
    brief_t1 = money(brief_plan.get("t1"))
    brief_t2 = money(brief_plan.get("t2"))
    brief_thesis = (
        f"A {brief_side} research setup based on a {brief_tf} {brief_zone_type} zone. "
        "The deterministic engine owns every price level; this workspace explains the decision without changing it."
        if brief_candidate else
        "Waiting for the canonical engine to produce a setup worth explaining. No trade is manufactured to fill the screen."
    )
    brief_action = {
        "APPROACHING": "Let price come to the zone. Do not chase. Wait for confirmation and execution viability.",
        "IN ZONE": "Price is testing structure. A touch alone is not permission to enter.",
        "QUALIFIED": "Structure is provisionally qualified. Verified V5 evidence must still authorize the grade.",
    }.get(brief_lifecycle, "Observe the market and wait for every deterministic gate to become explicit.")

    st.markdown("""
    <style>
    .tp-pw{border:0;border-radius:0;background:radial-gradient(circle at 72% 3%,rgba(30,91,151,.12),transparent 34%),linear-gradient(145deg,#07111d,#0a1522 58%,#07101a);padding:22px 22px 26px;color:#eef4fb;box-shadow:none}
    .tp-pw-tag{display:inline-block;background:#28683d;border:1px solid #3d9859;color:#b7f4c2;border-radius:3px;padding:3px 8px;font-size:9px;font-weight:900;letter-spacing:.08em}.tp-pw-tag.preview{background:#183955;border-color:#2e6691;color:#91caf7}
    .tp-pw-title{font-size:24px;font-weight:950;margin:7px 0 2px}.tp-pw-sub{font-size:12px;color:#91a4b8;max-width:760px;line-height:1.5}
    .tp-pw-grid{display:grid;grid-template-columns:1.22fr .98fr;gap:24px;margin-top:20px}.tp-pw-block{margin-bottom:20px}.tp-pw-head{font-size:14px;font-weight:900;letter-spacing:.025em;margin-bottom:8px}.tp-pw-blue{color:#58b5ff;margin-right:8px}.tp-pw-red{color:#ff5c58;margin-right:8px}.tp-pw-copy{font-size:13px;line-height:1.68;color:#c1ccd8;padding-left:23px}
    .tp-pw-roadmap{display:grid;grid-template-columns:1fr 1fr;gap:9px 22px;padding-left:22px}.tp-pw-road{border-left:1px solid #34516c;padding:3px 0 6px 14px;min-height:48px}.tp-pw-road b{display:block;font-size:12px;color:#f6f9fd}.tp-pw-road span{font-size:11px;color:#8fa0b2}
    .tp-pw-card{border:1px solid #2b4056;border-radius:6px;background:rgba(13,26,41,.76);padding:13px;margin-bottom:12px}.tp-pw-card-title{font-size:12px;font-weight:900;letter-spacing:.04em;margin-bottom:10px}
    .tp-pw-score{display:grid;grid-template-columns:116px 1fr;align-items:center;gap:12px}.tp-pw-ring{--value:0%;width:94px;height:94px;border-radius:50%;background:conic-gradient(#58ca6d var(--value),#26394b 0);display:flex;align-items:center;justify-content:center;position:relative;margin:auto}.tp-pw-ring:after{content:'';position:absolute;width:73px;height:73px;background:#0b1724;border-radius:50%}.tp-pw-ring-text{z-index:2;text-align:center;font-size:25px;font-weight:950;line-height:1}.tp-pw-ring-text small{display:block;font-size:7px;color:#aab7c5;margin-top:5px;letter-spacing:.08em}
    .tp-pw-check{font-size:12px;color:#d1dae4;margin:6px 0}.tp-pw-ok{color:#58cf70;margin-right:7px}.tp-pw-wait{color:#708398;margin-right:7px}.tp-pw-info{display:grid;grid-template-columns:1fr 1fr;gap:8px 18px}.tp-pw-info-row{display:flex;justify-content:space-between;border-bottom:1px solid #1c2d3e;padding-bottom:5px;color:#91a2b4;font-size:11px}.tp-pw-info-row b{color:#eef3f9;text-align:right}.tp-pw-long{color:#57d377!important}.tp-pw-short{color:#ff625f!important}
    .tp-pw-insight{border:1px solid #3b6b9c;border-radius:6px;background:linear-gradient(90deg,rgba(31,87,143,.24),rgba(12,29,47,.68));padding:12px 15px;margin-top:5px}.tp-pw-insight b{font-size:12px;color:#62b4ff;letter-spacing:.06em}.tp-pw-insight div{font-size:11px;color:#bfccda;margin-top:5px;line-height:1.55}
    .tp-pw-metrics{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin:12px 0 14px}.tp-pw-metric{border:1px solid #293c50;border-radius:6px;background:linear-gradient(145deg,#111e2d,#0a1420);padding:11px 12px;height:92px;position:relative;overflow:hidden}.tp-pw-metric label{display:block;font-size:10px;color:#94a4b6;letter-spacing:.05em}.tp-pw-metric strong{display:block;font-size:18px;margin-top:6px}.tp-pw-metric .pending{font-size:14px;color:#8294a8}.tp-pw-spark{position:absolute;left:9px;right:9px;bottom:7px;height:22px}.tp-pw-spark svg{width:100%;height:100%}.tp-pw-green{color:#58d475}.tp-pw-redtext{color:#ff615d}.tp-pw-blue-text{color:#61b3ff}
    .tp-pw-tabs{display:grid;grid-template-columns:repeat(6,1fr);border:1px solid #293d52;border-radius:5px;background:#091421;margin:0 0 8px}.tp-pw-tab{padding:10px 7px;text-align:center;font-size:11px;color:#aab7c5;border-bottom:2px solid transparent}.tp-pw-tab.active{color:#7dc3ff;border-bottom-color:#56adf5;background:#0d1b2b}
    .tp-pw-analysis{display:grid;grid-template-columns:.76fr 1.24fr;gap:10px}.tp-pw-panel{border:1px solid #293d52;border-radius:6px;background:rgba(10,21,34,.84);padding:14px}.tp-pw-panel h4{font-size:12px;margin:0 0 11px;color:#f0f5fa}.tp-pw-params{display:grid;grid-template-columns:repeat(2,1fr);gap:7px}.tp-pw-field{border:1px solid #26394d;border-radius:5px;padding:8px;background:#0d1927}.tp-pw-field span{display:block;font-size:9px;color:#8193a6}.tp-pw-field b{font-size:13px;color:#dbe4ee}.tp-pw-table{width:100%;border-collapse:collapse;font-size:10px}.tp-pw-table td{padding:5px 6px;border-bottom:1px solid #1e3042}.tp-pw-table td:first-child{color:#9cacbd}.tp-pw-table td:last-child{text-align:right;color:#8799ac}.tp-pw-chart{height:270px;border-left:1px solid #31445a;border-bottom:1px solid #31445a;background:repeating-linear-gradient(to bottom,transparent 0,transparent 41px,rgba(55,77,101,.28) 42px);position:relative}.tp-pw-chart svg{position:absolute;inset:10px;width:calc(100% - 20px);height:calc(100% - 20px)}.tp-pw-chart-note{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#71869b;font-size:12px;font-weight:800;letter-spacing:.05em}.tp-pw-months{display:grid;grid-template-columns:repeat(12,1fr);height:130px;align-items:end;gap:8px;border-bottom:1px solid #31445a;padding:0 8px}.tp-pw-month{background:#263c52;min-height:5px;border-radius:2px 2px 0 0;position:relative}.tp-pw-month:after{content:attr(data-m);position:absolute;top:calc(100% + 7px);left:50%;transform:translateX(-50%);font-size:7px;color:#718398}
    .tp-pw-bottom{display:grid;grid-template-columns:1fr 1.15fr 1.15fr;gap:0;border:1px solid #293d52;border-radius:6px;background:#0a1522;margin-top:10px}.tp-pw-bottom>div{padding:14px;border-right:1px solid #293d52}.tp-pw-bottom>div:last-child{border-right:0}.tp-pw-bottom h4{font-size:12px;margin:0 0 13px}.tp-pw-donut{width:94px;height:94px;border-radius:50%;background:conic-gradient(#263b50 0 100%);position:relative;margin:5px auto}.tp-pw-donut:after{content:'';position:absolute;inset:18px;background:#0a1522;border-radius:50%}.tp-pw-bar-row{display:grid;grid-template-columns:55px 1fr 42px;align-items:center;gap:8px;font-size:10px;margin:9px 0;color:#aab7c5}.tp-pw-bar{height:10px;background:#17283a;border-radius:2px;overflow:hidden}.tp-pw-bar span{display:block;height:100%;background:#385a75}.tp-pw-empty{text-align:center;color:#71869b;font-size:11px;margin-top:10px}
    @media(max-width:700px){.tp-pw-grid,.tp-pw-analysis{grid-template-columns:1fr}.tp-pw-metrics{grid-template-columns:repeat(2,1fr)}.tp-pw-tabs{grid-template-columns:repeat(3,1fr)}.tp-pw-bottom{grid-template-columns:1fr}.tp-pw-bottom>div{border-right:0;border-bottom:1px solid #293d52}}
    @media print {
      html,body,[data-testid="stAppViewContainer"],[data-testid="stMain"],.stApp{background:#07111d!important;-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important}
      [data-testid="stHeader"],header{background:#07111d!important}
      .tp-pw{background:radial-gradient(circle at 72% 3%,rgba(30,91,151,.12),transparent 34%),linear-gradient(145deg,#07111d,#0a1522 58%,#07101a)!important;padding:16px!important;color:#eef4fb!important}
      .tp-pw-grid{grid-template-columns:1.22fr .98fr!important;gap:20px!important}
      .tp-pw-metrics{grid-template-columns:repeat(6,1fr)!important;gap:7px!important}
      .tp-pw-tabs{grid-template-columns:repeat(6,1fr)!important}
      .tp-pw-analysis{grid-template-columns:.76fr 1.24fr!important;gap:8px!important}
      .tp-pw-bottom{grid-template-columns:1fr 1.15fr 1.15fr!important}
      .tp-pw-bottom>div{border-right:1px solid #293d52!important;border-bottom:0!important}
      .tp-pw-title{font-size:22px!important}.tp-pw-sub{font-size:10px!important}
      .tp-pw-head{font-size:11px!important}.tp-pw-copy{font-size:10px!important;line-height:1.5!important}
      .tp-pw-road b{font-size:9px!important}.tp-pw-road span{font-size:8px!important}
      .tp-pw-card-title{font-size:9px!important}.tp-pw-check{font-size:8px!important}.tp-pw-info-row{font-size:8px!important}
      .tp-pw-metric{height:70px!important;padding:8px!important}.tp-pw-metric label{font-size:7px!important}.tp-pw-metric strong{font-size:14px!important}
      .tp-pw-panel{padding:10px!important}.tp-pw-chart{height:220px!important}.tp-pw-months{height:90px!important}
      .tp-pw-insight{padding:9px 12px!important}.tp-pw-insight b{font-size:9px!important}.tp-pw-insight div{font-size:8px!important}
      .tp-pw-tab{font-size:8px!important;padding:8px 4px!important}
    }
    </style>
    """, unsafe_allow_html=True)

    score_css = min(max(brief_score or 0, 0), 100)
    status_class = "" if brief_status == "WATCH" else " preview"
    st.markdown(f"""
    <div class="tp-pw">
      <span class="tp-pw-tag{status_class}">{brief_status}</span>
      <div class="tp-pw-title">PROFESSOR TRADE BRIEF</div>
      <div class="tp-pw-sub">A complete decision workspace for the selected research setup. Verified modules populate automatically as they pass audit.</div>
      <div class="tp-pw-grid">
        <div>
          <div class="tp-pw-block"><div class="tp-pw-head"><span class="tp-pw-blue">⌁</span>TRADE THESIS</div><div class="tp-pw-copy">{brief_thesis}</div></div>
          <div class="tp-pw-block"><div class="tp-pw-head"><span class="tp-pw-blue">◎</span>WHY THIS ENTRY</div><div class="tp-pw-copy">Entry at {brief_entry} is owned by the canonical zone and lifecycle. The system must confirm price behavior before the setup becomes executable.</div></div>
          <div class="tp-pw-block"><div class="tp-pw-head"><span class="tp-pw-blue">♧</span>TARGETS &amp; TRADE MANAGEMENT ROADMAP</div><div class="tp-pw-roadmap">
            <div class="tp-pw-road"><b>T1: {brief_t1}</b><span>First deterministic objective</span></div><div class="tp-pw-road"><b>INVALIDATION: {brief_stop}</b><span>Structure fails beyond this level</span></div>
            <div class="tp-pw-road"><b>T2: {brief_t2}</b><span>Secondary deterministic objective</span></div><div class="tp-pw-road"><b>STOP LOSS: {brief_stop}</b><span>Never widened to rescue a trade</span></div>
            <div class="tp-pw-road"><b>T3: --</b><span>Module not yet promoted</span></div><div class="tp-pw-road"><b>R:R POTENTIAL: {_brief_value(brief_rr, lambda v:f'{v:.2f}')}</b><span>Pending V5 execution validation</span></div>
          </div></div>
        </div>
        <div>
          <div class="tp-pw-block"><div class="tp-pw-head"><span class="tp-pw-red">⬡</span>WHY THIS STOP</div><div class="tp-pw-copy">The stop sits beyond deterministic structural invalidation. V5 must verify that its distance survives normal tick noise, spread and one-minute first-touch ordering.</div></div>
          <div class="tp-pw-card"><div class="tp-pw-card-title">STRUCTURE SCORE (NOT WIN PROBABILITY)</div><div class="tp-pw-score">
            <div class="tp-pw-ring" style="--value:{score_css}%"><div class="tp-pw-ring-text">{_brief_value(brief_score,lambda v:f'{v/10:.1f}')}<small>STRUCTURE / 10</small></div></div>
            <div><div class="tp-pw-check"><span class="tp-pw-ok">●</span>Canonical structure</div><div class="tp-pw-check"><span class="tp-pw-ok">●</span>Zone quality {_brief_value(brief_quality,lambda v:f'{v:.0f}')}</div><div class="tp-pw-check"><span class="tp-pw-ok">●</span>Freshness {_brief_value(brief_fresh,lambda v:f'{v:.0f}')}</div><div class="tp-pw-check"><span class="tp-pw-wait">○</span>V5 evidence pending</div><div class="tp-pw-check"><span class="tp-pw-wait">○</span>Execution viability pending</div></div>
          </div></div>
          <div class="tp-pw-card"><div class="tp-pw-card-title">KEY INFORMATION</div><div class="tp-pw-info">
            <div class="tp-pw-info-row"><span>Symbol</span><b>{brief_symbol}</b></div><div class="tp-pw-info-row"><span>Entry Type</span><b>Canonical Zone</b></div>
            <div class="tp-pw-info-row"><span>Timeframe</span><b>{brief_tf}</b></div><div class="tp-pw-info-row"><span>Market Context</span><b>{brief_zone_type}</b></div>
            <div class="tp-pw-info-row"><span>Direction</span><b class="{brief_direction_class}">{brief_side}</b></div><div class="tp-pw-info-row"><span>Lifecycle</span><b>{brief_lifecycle}</b></div>
            <div class="tp-pw-info-row"><span>MTF Alignment</span><b>{brief_mtf}</b></div><div class="tp-pw-info-row"><span>Evidence</span><b>{'LIVE PROMOTED' if data_truth.live_promotion else 'RESEARCH ONLY'}</b></div>
          </div></div>
        </div>
      </div>
      <div class="tp-pw-insight"><b>★ &nbsp; PROFESSOR INSIGHT</b><div>{brief_action} The Professor explains the plan; it never invents or moves deterministic prices.</div></div>
      </div>
    """, unsafe_allow_html=True)

    if brief_candidate:
        if st.button("INSPECT THIS SETUP", key=f"pw_inspect_{brief_symbol}_{brief_candidate.candidate_id}", width="stretch"):
            brief_display_tf = {"D":"1D","W":"1W"}.get(brief_candidate.timeframe,brief_candidate.timeframe)
            st.session_state.active_symbol = brief_symbol
            if brief_display_tf in CHART_TIMEFRAMES:
                st.session_state.chart_tf = brief_display_tf
            st.session_state.focused_candidate_id = brief_candidate.candidate_id
            st.session_state[f"preferred_candidate_{brief_display_tf}"] = brief_candidate.candidate_id
            st.rerun()
    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    st.divider()
    render_trade_readiness(market_state)

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
        ready_candidates = canonical_candidates
        selected_candidate = next((c for c in ready_candidates if c.is_selected_zone), None)
        execution_snapshot = build_execution_lifecycle(market_state, selected_candidate)
        st.success("BROKER GATE: ELIGIBLE FOR ORDER ROUTING - account risk/quantity authorization still required.")
        with st.expander("Broker-ready deterministic order packet", expanded=False):
            st.json(broker_order_intent(market_state, selected_candidate), expanded=False)

# ---------------------------------------------------------------------
# JOURNAL TAB
# ---------------------------------------------------------------------

with journal_tab:
    st.write("")
    render_section("TRADE MEMORY", "Journal")

    try:
        ensure_tracking_schema()
    except Exception as exc:
        st.caption(f"Tracker schema unavailable: {exc}")

    journal_trades_tab, journal_performance_tab = st.tabs(
        ["TRADE JOURNAL", "PERFORMANCE ANALYTICS"]
    )

    with journal_trades_tab:
        refresh_col, info_col = st.columns([1, 2])
        with refresh_col:
            if st.button("REFRESH TRACKED TRADES", width="stretch", key="refresh_tracked_journal"):
                try:
                    result = refresh_tracked_trades()
                    if result["errors"]:
                        st.warning(f"Checked {result['checked']} tracked trades; {len(result['errors'])} need attention.")
                    else:
                        st.success(f"Checked {result['checked']} tracked trades. Journal is current.")
                    st.cache_data.clear()
                except Exception as exc:
                    st.error(f"Tracker refresh failed: {exc}")
        with info_col:
            st.caption("PENDING ENTRY -> OPEN -> WIN/LOSS. Same-candle stop/target ambiguity is resolved STOP-first.")
        st.caption(
            "Review individual trades, outcomes, exits, and realized P&L."
        )

        try:
            trades_df = get_all_trades()

            if len(trades_df) > 0:
                for _, trade_row in trades_df.head(30).iterrows():
                    outcome = str(trade_row["outcome"])
                    tracking_status = str(trade_row.get("tracking_status", "") or "") if hasattr(trade_row, "get") else ""
                    display_status = tracking_status if tracking_status and tracking_status != "nan" else outcome
                    title = (
                        f"#{trade_row['id']} / {trade_row['symbol']} {trade_row['direction']} "
                        f"@ {money(trade_row['entry'])} / "
                        f"Grade {trade_row['grade']} / {display_status.replace('_', ' ')}"
                    )

                    with st.expander(title):
                        c1, c2 = st.columns(2)

                        with c1:
                            st.write(f"Entry: {money(trade_row['entry'])}")
                            st.write(f"Stop: {money(trade_row['stop'])}")
                            st.write(f"Target: {money(trade_row['target'])}")

                        with c2:
                            st.write(f"Tracking: {display_status.replace('_', ' ')}")
                            st.write(f"Outcome: {outcome}")
                            if "setup_score" in trade_row.index and str(trade_row.get("setup_score")) not in ("None", "nan"):
                                st.write(f"Setup Score: {float(trade_row.get('setup_score')):.1f}/10")
                            if "r_multiple" in trade_row.index and str(trade_row.get("r_multiple")) not in ("None", "nan"):
                                st.write(f"Result: {float(trade_row.get('r_multiple')):.2f}R")

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

    with journal_performance_tab:
        render_section("EDGE TRACKING", "Performance Analytics")

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
                        st.dataframe(dna_df, width="stretch")
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
    # BACKTEST WORKSPACE ORDER - V3.3: CONTROLS / VISUAL BRIEF / DETAILS
    # RESTORED MANUAL BACKTEST LAB - V3.2
    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
    # V3.2C - high-fidelity Backtest Lab research terminal.
    # Visual-only rebuild: canonical V3.2A replay/evidence backend is preserved.
    st.markdown(r"""
    <style>
    /* ---- Backtest Lab design system ---- */
    div[data-testid="stTabs"] div[role="tabpanel"] {padding-top:.15rem;}
    .bt-shell{font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif;color:#f5f7fa}
    .bt-hero{position:relative;overflow:hidden;border:1px solid #243141;border-radius:12px;padding:22px 24px;margin:4px 0 14px;background:
      radial-gradient(circle at 78% 0%,rgba(236,183,54,.20),transparent 24%),
      linear-gradient(90deg,#070c12 0%,#09111b 62%,#070b11 100%);box-shadow:inset 0 1px rgba(255,255,255,.02),0 12px 32px rgba(0,0,0,.22)}
    .bt-hero:after{content:"";position:absolute;right:18%;top:-45px;width:270px;height:140px;opacity:.42;background:linear-gradient(160deg,transparent 49%,#ff4b55 50%,transparent 51%);filter:drop-shadow(0 0 7px #c9323d);transform:rotate(-7deg)}
    .bt-hero-title{font-size:2.05rem;font-weight:950;letter-spacing:.015em;line-height:1.05}.bt-hero-sub{color:#9da8b6;font-size:.94rem;margin-top:7px}
    .bt-panel{border:1px solid #243141;border-radius:12px;background:linear-gradient(145deg,#0a111a,#080e15);padding:16px 18px;margin:0 0 12px;box-shadow:inset 0 1px rgba(255,255,255,.018)}
    .bt-step{color:#ff5b65;font-size:.82rem;font-weight:950;letter-spacing:.045em;margin:0 0 6px}.bt-copy{color:#b4bdc9;font-size:.82rem;margin-bottom:8px}
    .bt-card{border:1px solid #263342;border-radius:9px;background:linear-gradient(145deg,#0a111a,#080e15);padding:13px 14px;min-height:76px;box-shadow:inset 0 1px rgba(255,255,255,.018)}
    .bt-card-label{font-size:.63rem;color:#c2c9d2;font-weight:900;letter-spacing:.065em}.bt-card-value{font-size:1.55rem;font-weight:950;margin-top:6px;line-height:1.05}
    .bt-gold{color:#ff5b65}.bt-green{color:#31d56c}.bt-red{color:#ff554d}.bt-blue{color:#49a6ff}.bt-purple{color:#b46cff}.bt-muted{color:#8995a4;font-size:.68rem}.bt-active{color:#31d56c;font-weight:900}
    .bt-info{border:1px solid #2a3746;border-radius:9px;background:#09111a;padding:12px 14px;min-height:73px}.bt-info-title{color:#ff5b65;font-size:.66rem;font-weight:950;letter-spacing:.055em}.bt-info-copy{color:#aab4c1;font-size:.70rem;line-height:1.45;margin-top:4px}
    .bt-result-head{color:#ff5b65;font-size:.83rem;font-weight:950;letter-spacing:.045em;margin:10px 0 8px}.bt-chart-card{border:1px solid #263342;border-radius:10px;background:#081019;padding:9px 13px 12px;min-height:300px}.bt-chart-title{color:#ff5b65;font-size:.73rem;font-weight:950;letter-spacing:.035em;margin:2px 0 8px}
    .bt-insight{border-bottom:1px solid #1d2935;padding:10px 2px;color:#d1d6dd;font-size:.76rem;line-height:1.45}.bt-insight:last-child{border-bottom:0}.bt-bullet{display:inline-flex;width:22px;height:22px;border:1px solid #c9323d;border-radius:50%;align-items:center;justify-content:center;color:#ff5b65;margin-right:8px;font-size:.7rem}
    .bt-edge{text-align:center;padding:8px 0 2px}.bt-edge-label{font-size:.65rem;color:#c3cbd5;font-weight:900}.bt-edge-grade{font-size:3.35rem;font-weight:950;line-height:1;color:#4bd36d;text-shadow:0 0 18px rgba(75,211,109,.16)}.bt-edge-copy{font-size:.72rem;color:#40d766;font-weight:850;margin-top:5px}
    .bt-empty{height:210px;display:flex;align-items:center;justify-content:center;text-align:center;color:#657384;font-size:.76rem;border:1px dashed #22303e;border-radius:8px;background:linear-gradient(180deg,rgba(12,20,30,.35),rgba(6,11,17,.35))}
    .bt-footnote{font-size:.66rem;color:#758191;margin:5px 0 8px}
    /* Native controls, tuned to mockup */
    div[data-testid="stSelectbox"] label,div[data-testid="stSlider"] label{font-size:.64rem!important;font-weight:900!important;letter-spacing:.045em!important;color:#e7eaf0!important}
    div[data-baseweb="select"]>div{background:#090f17!important;border-color:#2a3746!important;min-height:42px!important;border-radius:7px!important}
    div[data-testid="stSlider"]{padding-top:0!important}
    div[data-testid="stButton"]>button{border-radius:6px!important;min-height:43px!important;font-size:.72rem!important;font-weight:900!important;letter-spacing:.04em!important}
    div[data-testid="stButton"]>button[kind="primary"]{background:linear-gradient(90deg,#b92733 0%,#e33f49 45%,#ff6b74 72%,#c9323d 100%)!important;color:#ffffff!important;border:1px solid #ff8c93!important;box-shadow:0 0 20px rgba(255,75,85,.16)!important}
    div[data-testid="stDataFrame"]{border:1px solid #253240;border-radius:8px;overflow:hidden}
    /* Plotly/Streamlit chart framing */
    div[data-testid="stVegaLiteChart"],div[data-testid="stArrowVegaLiteChart"]{background:#081019;border-radius:8px}
    </style>
    <div class="bt-shell">
      <div class="bt-hero">
        <div class="bt-hero-title">BACKTEST LAB</div>
        <div class="bt-hero-sub">Test. Validate. Refine. Build Edge with Data.</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    try:
        ev = get_evidence_stats()
    except Exception:
        ev = {"runs": 0, "observations": 0, "resolved": 0}

    # Header warehouse status mirrors the reference terminal without fabricating results.
    wh1, wh2, wh3, wh4 = st.columns([1.0, 1.0, 1.0, 1.15])
    with wh1:
        st.markdown(f'<div class="bt-card"><div class="bt-card-label">RESEARCH RUNS</div><div class="bt-card-value">{ev["runs"]:,}</div></div>', unsafe_allow_html=True)
    with wh2:
        st.markdown(f'<div class="bt-card"><div class="bt-card-label">UNIQUE SETUPS</div><div class="bt-card-value bt-gold">{ev["observations"]:,}</div></div>', unsafe_allow_html=True)
    with wh3:
        st.markdown(f'<div class="bt-card"><div class="bt-card-label">RESOLVED OUTCOMES</div><div class="bt-card-value bt-green">{ev["resolved"]:,}</div></div>', unsafe_allow_html=True)
    with wh4:
        st.markdown(f'<div class="bt-card"><div class="bt-card-label">EVIDENCE WAREHOUSE &nbsp; <span class="bt-active">Active</span></div><div class="bt-muted" style="margin-top:9px">Unique setups: <b style="color:#f4f6f8">{ev["observations"]:,}</b><br>De-duplicated research evidence</div></div>', unsafe_allow_html=True)

    st.markdown('<div class="bt-panel"><div class="bt-step">1. DESIGN YOUR EXPERIMENT</div><div class="bt-copy">Configure a legacy V3 backtest experiment. V4 evidence-qualified grading is validated separately and is never inferred from raw score alone.</div></div>', unsafe_allow_html=True)

    symbols = get_enabled_symbols()
    c1, c2, c3, c4, c5 = st.columns([1.25, 1.0, 1.35, 1.18, 1.15])
    with c1:
        bt_symbol = st.selectbox("MARKET", symbols, index=symbols.index("CL") if "CL" in symbols else 0, format_func=lambda x: {"GC":"Gold","SI":"Silver","ES":"S&P 500","NQ":"Nasdaq 100","YM":"Dow","RTY":"Russell 2000","CL":"Crude Oil","NG":"Natural Gas"}.get(x,x), key="bt_market")
    with c2:
        scopes = list(TF_SETS.keys())
        bt_scope = st.selectbox("TIMEFRAME SCOPE", scopes, index=scopes.index("1H+") if "1H+" in scopes else 0, key="bt_scope")
    with c3:
        bt_score = st.slider("MIN SETUP QUALITY", 5.5, 10.0, 9.4, 0.1, key="bt_score")
        st.markdown(f'<div class="bt-muted" style="text-align:center;margin-top:-7px"><b style="font-size:1.05rem;color:#f4f6f8">{bt_score:.1f} / 10+</b></div>', unsafe_allow_html=True)
    with c4:
        bt_direction = st.selectbox("DIRECTION", ["BOTH", "LONG", "SHORT"], format_func=lambda x: x.title(), key="bt_direction")
    with c5:
        bt_days = st.selectbox(
            "LOOKBACK PERIOD",
            [1, 7, 14, 30, 60, 90, 180, 365, 730],
            index=2,
            format_func=lambda x: "1 Day" if x == 1 else ("1 Week" if x == 7 else ("2 Weeks" if x == 14 else f"{x} Days")),
            key="bt_days",
        )

    tf_copy = {"15m+":"15m / 1H / 4H / Daily","1H+":"1H / 4H / Daily","4H+":"4H / Daily"}.get(bt_scope, bt_scope)
    i1,i2,i3,i4 = st.columns(4)
    with i1:
        st.markdown(f'<div class="bt-info"><div class="bt-info-title">TIMEFRAMES INCLUDED</div><div class="bt-info-copy">> &nbsp; {tf_copy}</div></div>', unsafe_allow_html=True)
    with i2:
        st.markdown(f'<div class="bt-info"><div class="bt-info-title">SETUP GRADING</div><div class="bt-info-copy">Same 10-Point System Used Live<br>Structure | Confluence | Execution | Risk</div></div>', unsafe_allow_html=True)
    with i3:
        st.markdown('<div class="bt-info"><div class="bt-info-title">EVIDENCE COLLECTION</div><div class="bt-info-copy">All results stored in Evidence Warehouse<br>Duplicates automatically de-duplicated</div></div>', unsafe_allow_html=True)
    with i4:
        st.markdown('<div class="bt-info"><div class="bt-info-title">DATA INTEGRITY</div><div class="bt-info-copy">Point-in-Time Replay Engine<br>No lookahead bias. Ever.</div></div>', unsafe_allow_html=True)

    if bt_scope in ("5m", "15m", "15m+") and bt_days > 60:
        st.warning("Intraday reference-data coverage may be shorter than the selected lookback. Available history will be reported; missing data is never fabricated.")

    run_col, save_col = st.columns([5.0, 1.05])
    with run_col:
        run_clicked = st.button(
            "RUN BACKTEST - CANONICAL ADAPTER REQUIRED",
            type="primary",
            width="stretch",
            key="run_backtest_lab",
            disabled=not allow_manual_backtest(),
            help="The previous button ran the legacy V3/Yahoo replay. It is blocked until the V5/V7 point-in-time database adapter is installed.",
        )
    with save_col:
        st.button("SAVE AS EXPERIMENT", width="stretch", disabled=True, help="Experiment presets are coming next.")
    st.markdown(f'<div class="bt-footnote">Hypothesis: <b>{bt_symbol}</b> &nbsp;|&nbsp; <b>{bt_scope}</b> &nbsp;|&nbsp; <b>{bt_score:.1f}+</b> &nbsp;|&nbsp; <b>{bt_days}d</b> &nbsp;|&nbsp; <b>{bt_direction.title()}</b></div>', unsafe_allow_html=True)

    st.info(
        "Manual controls are preserved, but execution is temporarily blocked because the old button used the V3/Yahoo replay. "
        "The newest V5/V7 research remains read-only until a query-compatible canonical adapter is validated."
    )
    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
    # Full-width Professor intelligence workspace. Widgets remain visible even
    # before their verified V5 backends are promoted; unavailable values stay blank.
    st.write("")
    watch_opportunities = elite_diagnostics.get("watch_opportunities", [])
    brief_opportunity = watch_opportunities[0] if watch_opportunities else None
    brief_candidate = focused_candidate
    brief_state = brief_opportunity.market_state if brief_opportunity else market_state
    brief_symbol = brief_opportunity.symbol if brief_opportunity else active_symbol
    brief_side = brief_opportunity.direction if brief_opportunity else (
        "LONG" if brief_candidate and str(brief_candidate.zone_type).lower() == "demand" else "SHORT"
    )
    brief_status = "WATCH" if brief_opportunity else "RESEARCH PREVIEW"
    try:
        brief_plan = planned_trade_metrics(brief_candidate, brief_state) if brief_candidate else {}
    except Exception:
        brief_plan = {}

    def _brief_value(value, formatter=None):
        if value is None:
            return "--"
        return formatter(value) if formatter else str(value)

    brief_score = safe_float(getattr(brief_candidate, "setup_score", None)) if brief_candidate else None
    brief_quality = safe_float(getattr(brief_candidate, "zone_quality_score", None)) if brief_candidate else None
    brief_fresh = safe_float(getattr(brief_candidate, "freshness_score", None)) if brief_candidate else None
    brief_rr = safe_float(getattr(brief_candidate, "projected_rr", None)) if brief_candidate else None
    brief_tf = str(getattr(brief_candidate, "timeframe", "--")) if brief_candidate else "--"
    brief_zone_type = str(getattr(brief_candidate, "zone_type", "--")).upper() if brief_candidate else "--"
    brief_lifecycle = str(getattr(brief_candidate, "lifecycle", "WAITING")).replace("_", " ") if brief_candidate else "WAITING"
    brief_mtf = (
        f"{brief_opportunity.mtf_aligned}/{brief_opportunity.mtf_total}"
        if brief_opportunity and brief_opportunity.mtf_total else "--"
    )
    brief_direction_class = "tp-pw-long" if brief_side == "LONG" else "tp-pw-short"
    brief_entry = money(brief_plan.get("entry"))
    brief_stop = money(brief_plan.get("stop"))
    brief_t1 = money(brief_plan.get("t1"))
    brief_t2 = money(brief_plan.get("t2"))
    brief_thesis = (
        f"A {brief_side} research setup based on a {brief_tf} {brief_zone_type} zone. "
        "The deterministic engine owns every price level; this workspace explains the decision without changing it."
        if brief_candidate else
        "Waiting for the canonical engine to produce a setup worth explaining. No trade is manufactured to fill the screen."
    )
    brief_action = {
        "APPROACHING": "Let price come to the zone. Do not chase. Wait for confirmation and execution viability.",
        "IN ZONE": "Price is testing structure. A touch alone is not permission to enter.",
        "QUALIFIED": "Structure is provisionally qualified. Verified V5 evidence must still authorize the grade.",
    }.get(brief_lifecycle, "Observe the market and wait for every deterministic gate to become explicit.")

    st.markdown("""
    <style>
    .tp-pw{border:0;border-radius:0;background:radial-gradient(circle at 72% 3%,rgba(30,91,151,.12),transparent 34%),linear-gradient(145deg,#07111d,#0a1522 58%,#07101a);padding:22px 22px 26px;color:#eef4fb;box-shadow:none}
    .tp-pw-tag{display:inline-block;background:#28683d;border:1px solid #3d9859;color:#b7f4c2;border-radius:3px;padding:3px 8px;font-size:9px;font-weight:900;letter-spacing:.08em}.tp-pw-tag.preview{background:#183955;border-color:#2e6691;color:#91caf7}
    .tp-pw-title{font-size:24px;font-weight:950;margin:7px 0 2px}.tp-pw-sub{font-size:12px;color:#91a4b8;max-width:760px;line-height:1.5}
    .tp-pw-grid{display:grid;grid-template-columns:1.22fr .98fr;gap:24px;margin-top:20px}.tp-pw-block{margin-bottom:20px}.tp-pw-head{font-size:14px;font-weight:900;letter-spacing:.025em;margin-bottom:8px}.tp-pw-blue{color:#58b5ff;margin-right:8px}.tp-pw-red{color:#ff5c58;margin-right:8px}.tp-pw-copy{font-size:13px;line-height:1.68;color:#c1ccd8;padding-left:23px}
    .tp-pw-roadmap{display:grid;grid-template-columns:1fr 1fr;gap:9px 22px;padding-left:22px}.tp-pw-road{border-left:1px solid #34516c;padding:3px 0 6px 14px;min-height:48px}.tp-pw-road b{display:block;font-size:12px;color:#f6f9fd}.tp-pw-road span{font-size:11px;color:#8fa0b2}
    .tp-pw-card{border:1px solid #2b4056;border-radius:6px;background:rgba(13,26,41,.76);padding:13px;margin-bottom:12px}.tp-pw-card-title{font-size:12px;font-weight:900;letter-spacing:.04em;margin-bottom:10px}
    .tp-pw-score{display:grid;grid-template-columns:116px 1fr;align-items:center;gap:12px}.tp-pw-ring{--value:0%;width:94px;height:94px;border-radius:50%;background:conic-gradient(#58ca6d var(--value),#26394b 0);display:flex;align-items:center;justify-content:center;position:relative;margin:auto}.tp-pw-ring:after{content:'';position:absolute;width:73px;height:73px;background:#0b1724;border-radius:50%}.tp-pw-ring-text{z-index:2;text-align:center;font-size:25px;font-weight:950;line-height:1}.tp-pw-ring-text small{display:block;font-size:7px;color:#aab7c5;margin-top:5px;letter-spacing:.08em}
    .tp-pw-check{font-size:12px;color:#d1dae4;margin:6px 0}.tp-pw-ok{color:#58cf70;margin-right:7px}.tp-pw-wait{color:#708398;margin-right:7px}.tp-pw-info{display:grid;grid-template-columns:1fr 1fr;gap:8px 18px}.tp-pw-info-row{display:flex;justify-content:space-between;border-bottom:1px solid #1c2d3e;padding-bottom:5px;color:#91a2b4;font-size:11px}.tp-pw-info-row b{color:#eef3f9;text-align:right}.tp-pw-long{color:#57d377!important}.tp-pw-short{color:#ff625f!important}
    .tp-pw-insight{border:1px solid #3b6b9c;border-radius:6px;background:linear-gradient(90deg,rgba(31,87,143,.24),rgba(12,29,47,.68));padding:12px 15px;margin-top:5px}.tp-pw-insight b{font-size:12px;color:#62b4ff;letter-spacing:.06em}.tp-pw-insight div{font-size:11px;color:#bfccda;margin-top:5px;line-height:1.55}
    .tp-pw-metrics{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin:12px 0 14px}.tp-pw-metric{border:1px solid #293c50;border-radius:6px;background:linear-gradient(145deg,#111e2d,#0a1420);padding:11px 12px;height:92px;position:relative;overflow:hidden}.tp-pw-metric label{display:block;font-size:10px;color:#94a4b6;letter-spacing:.05em}.tp-pw-metric strong{display:block;font-size:18px;margin-top:6px}.tp-pw-metric .pending{font-size:14px;color:#8294a8}.tp-pw-spark{position:absolute;left:9px;right:9px;bottom:7px;height:22px}.tp-pw-spark svg{width:100%;height:100%}.tp-pw-green{color:#58d475}.tp-pw-redtext{color:#ff615d}.tp-pw-blue-text{color:#61b3ff}
    .tp-pw-tabs{display:grid;grid-template-columns:repeat(6,1fr);border:1px solid #293d52;border-radius:5px;background:#091421;margin:0 0 8px}.tp-pw-tab{padding:10px 7px;text-align:center;font-size:11px;color:#aab7c5;border-bottom:2px solid transparent}.tp-pw-tab.active{color:#7dc3ff;border-bottom-color:#56adf5;background:#0d1b2b}
    .tp-pw-analysis{display:grid;grid-template-columns:.76fr 1.24fr;gap:10px}.tp-pw-panel{border:1px solid #293d52;border-radius:6px;background:rgba(10,21,34,.84);padding:14px}.tp-pw-panel h4{font-size:12px;margin:0 0 11px;color:#f0f5fa}.tp-pw-params{display:grid;grid-template-columns:repeat(2,1fr);gap:7px}.tp-pw-field{border:1px solid #26394d;border-radius:5px;padding:8px;background:#0d1927}.tp-pw-field span{display:block;font-size:9px;color:#8193a6}.tp-pw-field b{font-size:13px;color:#dbe4ee}.tp-pw-table{width:100%;border-collapse:collapse;font-size:10px}.tp-pw-table td{padding:5px 6px;border-bottom:1px solid #1e3042}.tp-pw-table td:first-child{color:#9cacbd}.tp-pw-table td:last-child{text-align:right;color:#8799ac}.tp-pw-chart{height:270px;border-left:1px solid #31445a;border-bottom:1px solid #31445a;background:repeating-linear-gradient(to bottom,transparent 0,transparent 41px,rgba(55,77,101,.28) 42px);position:relative}.tp-pw-chart svg{position:absolute;inset:10px;width:calc(100% - 20px);height:calc(100% - 20px)}.tp-pw-chart-note{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#71869b;font-size:12px;font-weight:800;letter-spacing:.05em}.tp-pw-months{display:grid;grid-template-columns:repeat(12,1fr);height:130px;align-items:end;gap:8px;border-bottom:1px solid #31445a;padding:0 8px}.tp-pw-month{background:#263c52;min-height:5px;border-radius:2px 2px 0 0;position:relative}.tp-pw-month:after{content:attr(data-m);position:absolute;top:calc(100% + 7px);left:50%;transform:translateX(-50%);font-size:7px;color:#718398}
    .tp-pw-bottom{display:grid;grid-template-columns:1fr 1.15fr 1.15fr;gap:0;border:1px solid #293d52;border-radius:6px;background:#0a1522;margin-top:10px}.tp-pw-bottom>div{padding:14px;border-right:1px solid #293d52}.tp-pw-bottom>div:last-child{border-right:0}.tp-pw-bottom h4{font-size:12px;margin:0 0 13px}.tp-pw-donut{width:94px;height:94px;border-radius:50%;background:conic-gradient(#263b50 0 100%);position:relative;margin:5px auto}.tp-pw-donut:after{content:'';position:absolute;inset:18px;background:#0a1522;border-radius:50%}.tp-pw-bar-row{display:grid;grid-template-columns:55px 1fr 42px;align-items:center;gap:8px;font-size:10px;margin:9px 0;color:#aab7c5}.tp-pw-bar{height:10px;background:#17283a;border-radius:2px;overflow:hidden}.tp-pw-bar span{display:block;height:100%;background:#385a75}.tp-pw-empty{text-align:center;color:#71869b;font-size:11px;margin-top:10px}
    @media(max-width:700px){.tp-pw-grid,.tp-pw-analysis{grid-template-columns:1fr}.tp-pw-metrics{grid-template-columns:repeat(2,1fr)}.tp-pw-tabs{grid-template-columns:repeat(3,1fr)}.tp-pw-bottom{grid-template-columns:1fr}.tp-pw-bottom>div{border-right:0;border-bottom:1px solid #293d52}}
    @media print {
      html,body,[data-testid="stAppViewContainer"],[data-testid="stMain"],.stApp{background:#07111d!important;-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important}
      [data-testid="stHeader"],header{background:#07111d!important}
      .tp-pw{background:radial-gradient(circle at 72% 3%,rgba(30,91,151,.12),transparent 34%),linear-gradient(145deg,#07111d,#0a1522 58%,#07101a)!important;padding:16px!important;color:#eef4fb!important}
      .tp-pw-grid{grid-template-columns:1.22fr .98fr!important;gap:20px!important}
      .tp-pw-metrics{grid-template-columns:repeat(6,1fr)!important;gap:7px!important}
      .tp-pw-tabs{grid-template-columns:repeat(6,1fr)!important}
      .tp-pw-analysis{grid-template-columns:.76fr 1.24fr!important;gap:8px!important}
      .tp-pw-bottom{grid-template-columns:1fr 1.15fr 1.15fr!important}
      .tp-pw-bottom>div{border-right:1px solid #293d52!important;border-bottom:0!important}
      .tp-pw-title{font-size:22px!important}.tp-pw-sub{font-size:10px!important}
      .tp-pw-head{font-size:11px!important}.tp-pw-copy{font-size:10px!important;line-height:1.5!important}
      .tp-pw-road b{font-size:9px!important}.tp-pw-road span{font-size:8px!important}
      .tp-pw-card-title{font-size:9px!important}.tp-pw-check{font-size:8px!important}.tp-pw-info-row{font-size:8px!important}
      .tp-pw-metric{height:70px!important;padding:8px!important}.tp-pw-metric label{font-size:7px!important}.tp-pw-metric strong{font-size:14px!important}
      .tp-pw-panel{padding:10px!important}.tp-pw-chart{height:220px!important}.tp-pw-months{height:90px!important}
      .tp-pw-insight{padding:9px 12px!important}.tp-pw-insight b{font-size:9px!important}.tp-pw-insight div{font-size:8px!important}
      .tp-pw-tab{font-size:8px!important;padding:8px 4px!important}
    }
    </style>
    """, unsafe_allow_html=True)

    score_css = min(max(brief_score or 0, 0), 100)
    status_class = "" if brief_status == "WATCH" else " preview"
    st.markdown("<div style='font-size:18px;font-weight:900;color:#f4f7fb;margin:8px 0 10px'>BACKTEST INTELLIGENCE</div>", unsafe_allow_html=True)
    st.markdown(f"""
    <div class="tp-pw">
      <div class="tp-pw-metrics">
        <div class="tp-pw-metric"><label>WIN RATE</label><strong class="pending">AWAITING V5</strong><div class="tp-pw-spark"><svg viewBox="0 0 100 20"><path d="M0 14 L100 14" stroke="#344b61" stroke-dasharray="4 4" fill="none"/></svg></div></div>
        <div class="tp-pw-metric"><label>PROFIT FACTOR</label><strong class="pending">AWAITING V5</strong><div class="tp-pw-spark"><svg viewBox="0 0 100 20"><path d="M0 14 L100 14" stroke="#344b61" stroke-dasharray="4 4" fill="none"/></svg></div></div>
        <div class="tp-pw-metric"><label>EXPECTANCY</label><strong class="pending">AWAITING V5</strong><div class="tp-pw-spark"><svg viewBox="0 0 100 20"><path d="M0 14 L100 14" stroke="#344b61" stroke-dasharray="4 4" fill="none"/></svg></div></div>
        <div class="tp-pw-metric"><label>MAX DRAWDOWN</label><strong class="pending">AWAITING V5</strong><div class="tp-pw-spark"><svg viewBox="0 0 100 20"><path d="M0 14 L100 14" stroke="#344b61" stroke-dasharray="4 4" fill="none"/></svg></div></div>
        <div class="tp-pw-metric"><label>TOTAL TRADES</label><strong class="pending">AWAITING V5</strong><div class="tp-pw-spark"><svg viewBox="0 0 100 20"><path d="M0 14 L100 14" stroke="#344b61" stroke-dasharray="4 4" fill="none"/></svg></div></div>
        <div class="tp-pw-metric"><label>RETURN</label><strong class="pending">AWAITING V5</strong><div class="tp-pw-spark"><svg viewBox="0 0 100 20"><path d="M0 14 L100 14" stroke="#344b61" stroke-dasharray="4 4" fill="none"/></svg></div></div>
      </div>
      <div class="tp-pw-tabs"><div class="tp-pw-tab active">BACKTEST RESULTS</div><div class="tp-pw-tab">TRADE HISTORY</div><div class="tp-pw-tab">PERFORMANCE</div><div class="tp-pw-tab">RISK ANALYSIS</div><div class="tp-pw-tab">HEATMAP</div><div class="tp-pw-tab">MONTHLY REPORT</div></div>
      <div class="tp-pw-analysis">
        <div>
          <div class="tp-pw-panel"><h4>BACKTEST PARAMETERS</h4><div class="tp-pw-params"><div class="tp-pw-field"><span>START DATE</span><b>--</b></div><div class="tp-pw-field"><span>END DATE</span><b>--</b></div><div class="tp-pw-field"><span>TIMEFRAME</span><b>{brief_tf}</b></div><div class="tp-pw-field"><span>CONTRACT</span><b>{brief_symbol}</b></div><div class="tp-pw-field"><span>SL (RISK)</span><b>1R</b></div><div class="tp-pw-field"><span>TARGETS</span><b>3R / 5R</b></div></div></div>
          <div class="tp-pw-panel" style="margin-top:10px"><h4>RESULTS SUMMARY</h4><table class="tp-pw-table"><tr><td>Total Net Profit</td><td>--</td></tr><tr><td>Gross Profit</td><td>--</td></tr><tr><td>Gross Loss</td><td>--</td></tr><tr><td>Profit Factor</td><td>--</td></tr><tr><td>Win Rate</td><td>--</td></tr><tr><td>Total Trades</td><td>--</td></tr><tr><td>Average Win</td><td>--</td></tr><tr><td>Average Loss</td><td>--</td></tr><tr><td>Expectancy</td><td>--</td></tr><tr><td>Max Drawdown</td><td>--</td></tr><tr><td>Wilson Lower Bound</td><td>--</td></tr></table><div class="tp-pw-empty">Verified results populate after V5 calibration.</div></div>
        </div>
        <div class="tp-pw-panel"><h4>EQUITY CURVE</h4><div class="tp-pw-chart"><svg viewBox="0 0 600 180" preserveAspectRatio="none"><path d="M0 155 C100 130,150 145,230 105 S380 100,460 55 S540 65,600 25" fill="none" stroke="#31506b" stroke-width="2" stroke-dasharray="6 7"/></svg><div class="tp-pw-chart-note">AWAITING VERIFIED V5 EQUITY SERIES</div></div><h4 style="margin-top:18px">MONTHLY PERFORMANCE (%)</h4><div class="tp-pw-months">{''.join(f'<div class="tp-pw-month" data-m="{m}"></div>' for m in ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'])}</div></div>
      </div>
      <div class="tp-pw-bottom">
        <div><h4>TRADE DISTRIBUTION</h4><div class="tp-pw-donut"></div><div class="tp-pw-empty">Winners / losers awaiting V5</div></div>
        <div><h4>RISK / REWARD DISTRIBUTION</h4><div class="tp-pw-bar-row"><span>3R+</span><div class="tp-pw-bar"><span style="width:0%"></span></div><b>--</b></div><div class="tp-pw-bar-row"><span>2R to 3R</span><div class="tp-pw-bar"><span style="width:0%"></span></div><b>--</b></div><div class="tp-pw-bar-row"><span>1R to 2R</span><div class="tp-pw-bar"><span style="width:0%"></span></div><b>--</b></div><div class="tp-pw-bar-row"><span>0R to 1R</span><div class="tp-pw-bar"><span style="width:0%"></span></div><b>--</b></div></div>
        <div><h4>SETUP QUALITY BREAKDOWN</h4><div class="tp-pw-bar-row"><span>A+ Setups</span><div class="tp-pw-bar"><span style="width:0%"></span></div><b>--</b></div><div class="tp-pw-bar-row"><span>A Setups</span><div class="tp-pw-bar"><span style="width:0%"></span></div><b>--</b></div><div class="tp-pw-bar-row"><span>B Setups</span><div class="tp-pw-bar"><span style="width:0%"></span></div><b>--</b></div><div class="tp-pw-bar-row"><span>C Setups</span><div class="tp-pw-bar"><span style="width:0%"></span></div><b>--</b></div></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    result = st.session_state.get("bt_last_result")
    st.markdown('<div class="bt-result-head">2. RESULTS OVERVIEW</div>', unsafe_allow_html=True)

    if result:
        resolved = int(result.get("resolved",0) or 0); wins = int(result.get("wins",0) or 0); losses = int(result.get("losses",0) or 0); unresolved = int(result.get("unresolved",0) or 0)
        wr=result.get("win_rate"); ar=result.get("avg_r"); pf=result.get("profit_factor"); dd=result.get("max_drawdown_r"); total_r=result.get("total_r")
        avg_rr = result.get("avg_rr") or result.get("average_rr")
        metrics=[
            ("TOTAL SETUPS", result.get("events",0), ""),
            ("WIN RATE", "--" if wr is None else f"{wr:.1f}%", "bt-green"),
            ("EXPECTANCY (R)", "--" if ar is None else f"{ar:+.2f}R", "bt-green" if (ar or 0)>=0 else "bt-red"),
            ("AVERAGE R:R", "--" if avg_rr is None else f"1:{float(avg_rr):.2f}", "bt-blue"),
            ("PROFIT FACTOR", "--" if pf is None else f"{pf:.2f}", "bt-purple"),
            ("MAX DRAWDOWN", f"{float(dd or 0):.1f}R", "bt-red"),
        ]
    else:
        resolved=wins=losses=unresolved=0; wr=ar=pf=dd=total_r=None
        metrics=[("TOTAL SETUPS","--",""),("WIN RATE","--","bt-green"),("EXPECTANCY (R)","--","bt-green"),("AVERAGE R:R","--","bt-blue"),("PROFIT FACTOR","--","bt-purple"),("MAX DRAWDOWN","--","bt-red")]

    metric_cols=st.columns(6)
    for col,(label,value,cls) in zip(metric_cols,metrics):
        with col:
            st.markdown(f'<div class="bt-card"><div class="bt-card-label">{label}</div><div class="bt-card-value {cls}">{value}</div></div>', unsafe_allow_html=True)

    chart1, chart2, chart3 = st.columns([1.02,1.32,1.02])
    with chart1:
        st.markdown('<div class="bt-chart-title">GRADE DISTRIBUTION</div>', unsafe_allow_html=True)
        gd=(result or {}).get("grade_distribution",{})
        if gd:
            gdf=pd.DataFrame({"Grade":list(gd.keys()),"Setups":list(gd.values())}).set_index("Grade")
            st.bar_chart(gdf,height=240)
            st.caption(f"Showing setups with grade {bt_score:.1f} and above")
        else:
            st.markdown('<div class="bt-empty">Run an experiment to reveal where qualifying setup grades cluster.</div>', unsafe_allow_html=True)
    with chart2:
        st.markdown('<div class="bt-chart-title">MONTHLY PERFORMANCE (R)</div>', unsafe_allow_html=True)
        mr=(result or {}).get("monthly_r",{})
        if mr:
            mdf=pd.DataFrame({"Month":list(mr.keys()),"R":list(mr.values())}).set_index("Month")
            st.line_chart(mdf,height=240)
        else:
            st.markdown('<div class="bt-empty">Monthly expectancy will build here from resolved point-in-time outcomes.</div>', unsafe_allow_html=True)
    with chart3:
        st.markdown('<div class="bt-chart-title">OUTCOME BREAKDOWN</div>', unsafe_allow_html=True)
        if result and (wins+losses+unresolved):
            odf=pd.DataFrame({"Outcome":["Wins","Losses","Unresolved"],"Count":[wins,losses,unresolved]}).set_index("Outcome")
            st.bar_chart(odf,height=240)
        else:
            st.markdown('<div class="bt-empty">Wins, losses and unresolved setups will appear after the run completes.</div>', unsafe_allow_html=True)

    low1, low2 = st.columns([1.0,1.25])
    with low1:
        st.markdown('<div class="bt-chart-title">RECENT EXPERIMENTS</div>', unsafe_allow_html=True)
        try:
            recent=get_recent_experiments(5)
            if recent:
                rows=[]
                for x in recent:
                    sm=x.get("summary",{}) or {}
                    rows.append({"Market":x["symbol"],"Scope":x["scope"],"Grade":f'{float(x["min_score"]):.1f}+',"Lookback":f'{x["days"]}d',"Direction":x["direction"],"Setups":str(sm.get("events","--")),"Avg R":sm.get("avg_r","--")})
                st.dataframe(pd.DataFrame(rows),width="stretch",hide_index=True)
            else:
                st.markdown('<div class="bt-empty" style="height:150px">Completed experiments will be saved here for comparison and reuse.</div>', unsafe_allow_html=True)
        except Exception:
            st.markdown('<div class="bt-empty" style="height:150px">Recent experiments become available when the evidence warehouse initializes.</div>', unsafe_allow_html=True)
    with low2:
        st.markdown('<div class="bt-chart-title">KEY INSIGHTS</div>', unsafe_allow_html=True)
        if result and resolved:
            edge="STRONG" if (ar or 0)>0.5 and (wr or 0)>=50 else "DEVELOPING" if (ar or 0)>0 else "WEAK"
            grade="A" if edge=="STRONG" else "B" if edge=="DEVELOPING" else "C"
            st.markdown(f'<div class="bt-insight"><span class="bt-bullet">+</span>High-quality <b>{bt_symbol} {bt_score:.1f}+</b> setups produced <b>{"--" if ar is None else f"{ar:+.2f}R"}</b> average expectancy across {resolved} resolved observations.</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="bt-insight"><span class="bt-bullet">></span>Historical sample profit factor: <b>{"--" if pf is None else f"{pf:.2f}"}</b>. Maximum observed drawdown: <b>{float(dd or 0):.1f}R</b>.</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="bt-edge"><div class="bt-edge-label">EDGE QUALITY</div><div class="bt-edge-grade">{grade}</div><div class="bt-edge-copy">{edge} STATISTICAL EDGE</div></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="bt-insight"><span class="bt-bullet">1</span>Choose the market, timeframe scope and minimum grade you would actually trade.</div>', unsafe_allow_html=True)
            st.markdown('<div class="bt-insight"><span class="bt-bullet">2</span>Run the canonical point-in-time replay. Repeated discoveries are de-duplicated automatically.</div>', unsafe_allow_html=True)
            st.markdown('<div class="bt-insight"><span class="bt-bullet">3</span>Results become evidence for research and future Professor analysis - never automatic strategy changes.</div>', unsafe_allow_html=True)
            st.markdown('<div class="bt-edge"><div class="bt-edge-label">EDGE QUALITY</div><div class="bt-edge-grade" style="color:#697788">-</div><div class="bt-muted">Run an experiment to score the evidence.</div></div>', unsafe_allow_html=True)

    if result:
        st.markdown(f'<div class="bt-footnote">Research Run {result.get("run_id","")[:10]} &nbsp;|&nbsp; Canonical grader &nbsp;|&nbsp; Point-in-time replay &nbsp;|&nbsp; De-duplicated evidence</div>', unsafe_allow_html=True)
        if result.get("errors"):
            st.warning("Some timeframe coverage was unavailable. Successful observations were preserved; unavailable data was not guessed.")

    with st.expander("HOW THE LAB BUILDS EVIDENCE"):
        st.markdown("""**Same grader, same language.** Historical setups use the same `/10` quality framework shown live.  
**No future candles.** Every evaluation is reconstructed point-in-time.  
**One setup = one observation.** Repeated discovery links to the same canonical evidence instead of inflating sample size.  
**Evidence, not self-modification.** Research is stored for later Professor analysis; it never silently rewrites Trading Pulse rules.""")

# ---------------------------------------------------------------------
# SYSTEM DIAGNOSTICS
# Hidden from beta navigation. Diagnostic backend remains available in code.
# ---------------------------------------------------------------------


# === V3.4 SELECTION STATE DESIGN SYSTEM ===
st.markdown("""
<style>

/* SELECTED CONTROLS
   Dark surface + Pulse red accent instead of solid red slabs */
div[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(
        180deg,
        rgba(255,75,85,0.14),
        rgba(255,75,85,0.055)
    ) !important;

    color: #ffffff !important;
    border: 1px solid rgba(255,75,85,0.82) !important;

    box-shadow:
        inset 0 0 0 1px rgba(255,255,255,0.025),
        0 0 12px rgba(255,75,85,0.08) !important;

    text-shadow: none !important;
}

/* SELECTED HOVER */
div[data-testid="stButton"] > button[kind="primary"]:hover {
    background: linear-gradient(
        180deg,
        rgba(255,75,85,0.22),
        rgba(255,75,85,0.09)
    ) !important;

    color: #ffffff !important;
    border-color: #ff7078 !important;

    box-shadow:
        inset 0 0 0 1px rgba(255,255,255,0.035),
        0 0 16px rgba(255,75,85,0.14) !important;
}

/* UNSELECTED CONTROLS */
div[data-testid="stButton"] > button[kind="secondary"] {
    background: #0b1017 !important;
    color: #c5cfdb !important;
    border: 1px solid #303a48 !important;
    box-shadow: none !important;
}

/* UNSELECTED HOVER */
div[data-testid="stButton"] > button[kind="secondary"]:hover {
    background: #111923 !important;
    color: #ffffff !important;
    border-color: #566274 !important;
}

/* KEYBOARD FOCUS */
div[data-testid="stButton"] > button:focus-visible {
    outline: 2px solid rgba(255,75,85,0.55) !important;
    outline-offset: 2px !important;
}

</style>
""", unsafe_allow_html=True)
# === END V3.4 SELECTION STATE DESIGN SYSTEM ===

# ---------------------------------------------------------------------
# FOOTER
# ---------------------------------------------------------------------

st.divider()
st.markdown(
    """
    <div class="tp-footer">
        THE TRADING PULSE / GOLD TRADING COACH V3.2D BETA UX /
        CANONICAL MARKETSTATE ARCHITECTURE /
        EDUCATIONAL MARKET-ANALYSIS SOFTWARE / NOT FINANCIAL ADVICE
    </div>
    """,
    unsafe_allow_html=True,
)









# ---------------------------------------------------------------------
# PROFESSOR / BEGINNER ACADEMY - V3.4 PASS 5
# ---------------------------------------------------------------------

with professor_tab:
    st.write("")
    render_section("AI FUTURES PROFESSOR", "Learn the Market. Then Practice the Process.")
    st.caption(
        "Beginner Academy teaches paper execution step by step. Live-market answers use "
        "the exact canonical MarketState already shown in Command Center."
    )

    academy_tab, ask_tab, analytics_tab = st.tabs(["BEGINNER ACADEMY", "ASK PROFESSOR", "RESEARCH ANALYTICS"])

    with academy_tab:
        lessons = academy_lessons()
        completed = set(st.session_state.get("academy_completed", []))
        st.progress(len(completed) / max(len(lessons), 1))
        st.caption(f"{len(completed)} OF {len(lessons)} LESSONS COMPLETED")

        for lesson in lessons:
            lesson_id = int(lesson["id"])
            done = lesson_id in completed
            marker = "COMPLETE" if done else f"LESSON {lesson_id}"
            with st.expander(f"{marker}  |  {lesson['title']}", expanded=(lesson_id == 1 and not completed)):
                st.markdown(f"**GOAL:** {lesson['goal']}")
                st.write(lesson["body"])
                st.info(f"CHECKPOINT: {lesson['check']}")
                if lesson_id == 2:
                    st.link_button("OPEN TRADINGVIEW", "https://www.tradingview.com/")
                if st.checkbox(
                    "I understand this lesson",
                    value=done,
                    key=f"academy_done_{lesson_id}",
                ):
                    completed.add(lesson_id)
                else:
                    completed.discard(lesson_id)

        st.session_state["academy_completed"] = sorted(completed)
        if len(completed) == len(lessons):
            st.success("BEGINNER ACADEMY COMPLETE - continue practicing with Paper Trading before considering live execution.")

    with ask_tab:
        st.markdown("### ASK ABOUT THE CURRENT SCREEN")
        st.caption(
            "The Professor may explain canonical Trading Pulse facts, but it cannot invent "
            "prices, zones, probabilities, entries, stops, or targets."
        )
        question = st.text_input(
            "Your question",
            placeholder="Example: Why is this setup waiting instead of ready?",
            key="professor_live_question",
        )
        if st.button("ASK PROFESSOR", type="primary", key="professor_ask_button"):
            packet = answer_question(question, market_state.professor_payload(), research_mode=True)
            st.session_state["professor_last_packet"] = packet

        packet = st.session_state.get("professor_last_packet")
        if packet:
            st.markdown(professor_md(packet.get("answer", "")))
            sources = packet.get("sources") or []
            if sources:
                with st.expander("GROUNDING SOURCES", expanded=False):
                    for source in sources:
                        label = source.get("title") or source.get("domain") or "FuturesProf source"
                        st.write(f"- {label} | {source.get('domain','')} | {source.get('source_type','GROUNDED')}")

        with st.expander("CANONICAL MARKETSTATE PACKET", expanded=False):
            st.json(market_state.professor_payload(), expanded=False)

    with analytics_tab:
        st.markdown("### PROFESSOR RESEARCH & LEARNING ANALYTICS")
        st.caption("Questions are telemetry. Research claims stay quarantined until reviewed; they do not silently become truth.")
        m = get_professor_metrics_cached()
        a1,a2,a3,a4,a5 = st.columns(5)
        a1.metric("QUESTIONS", m.get("questions",0))
        a2.metric("WEB RESEARCH", m.get("researched",0))
        a3.metric("RESEARCH RATE", f"{m.get('research_pct',0):.0f}%")
        a4.metric("KNOWLEDGE GAPS", m.get("knowledge_gaps",0))
        a5.metric("AVG SOURCES", f"{m.get('avg_sources',0):.1f}")
        claim_counts=m.get("claims",{}) or {}
        st.markdown("#### CLAIM VERIFICATION QUEUE")
        st.caption("PENDING is not learned truth. Promote only after checking evidence; reject conflicts or weak claims.")
        st.write(" · ".join(f"{k}: {v}" for k,v in sorted(claim_counts.items())) or "No research claims yet.")
        pending=get_pending_professor_claims(20)
        for claim in pending:
            with st.expander(f"{claim.get('verification_status')} · {claim.get('sources',0)} source(s) · claim {claim.get('id')}", expanded=False):
                st.write(claim.get("claim_text",""))
                c1,c2,c3,c4=st.columns(4)
                if c1.button("CORROBORATE", key=f"claim_cor_{claim['id']}"):
                    review_professor_claim(int(claim['id']),"CORROBORATED","Manual review: corroborated")
                    st.rerun()
                if c2.button("VERIFY", key=f"claim_ver_{claim['id']}"):
                    review_professor_claim(int(claim['id']),"VERIFIED","Manual review: verified")
                    st.rerun()
                if c3.button("CONFLICT", key=f"claim_con_{claim['id']}"):
                    review_professor_claim(int(claim['id']),"CONFLICTED","Manual review: conflicting evidence")
                    st.rerun()
                if c4.button("REJECT", key=f"claim_rej_{claim['id']}"):
                    review_professor_claim(int(claim['id']),"REJECTED","Manual review: rejected")
                    st.rerun()
        st.markdown("#### RECENT QUESTIONS")
        recent=get_recent_professor_questions(20)
        if recent:
            st.dataframe(recent, width="stretch", hide_index=True)
        else:
            st.caption("Ask the Professor questions to begin building coverage metrics.")
        if professor_research_available():
            st.success("OPENAI RESEARCH CONNECTION: READY")
        else:
            st.warning("OPENAI RESEARCH CONNECTION: API KEY NOT CONFIGURED")

    st.warning(
        "EDUCATION / PAPER PRACTICE: The Professor explains the system and futures concepts. "
        "It does not guarantee outcomes and does not place trades."
    )
