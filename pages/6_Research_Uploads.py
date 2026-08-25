"""Public research intake for The Trading Pulse.

Accepts public video/indicator links and optional small video files. Submissions
are evidence candidates only; they never modify trading rules automatically.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st


st.set_page_config(
    page_title="Research Uploads | The Trading Pulse",
    page_icon="TP",
    layout="wide",
    initial_sidebar_state="collapsed",
)

BRAND = "#ff4b55"
BG = "#07090d"
PANEL = "#0d1118"
PANEL_2 = "#111722"
BORDER = "#242c39"
TEXT = "#f5f7fa"
MUTED = "#aeb9c8"
MAX_FILE_MB = max(1, min(int(os.getenv("TP_RESEARCH_MAX_UPLOAD_MB", "25")), 100))
MAX_LINKS = 10
ALLOWED_EXTENSIONS = {"mp4", "mov", "m4v", "webm"}
ALLOWED_MIME_PREFIXES = ("video/",)
PROVIDER_HOSTS = {
    "TikTok": ("tiktok.com", "www.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"),
    "Instagram": ("instagram.com", "www.instagram.com"),
    "YouTube": ("youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"),
    "TradingView": ("tradingview.com", "www.tradingview.com"),
    "Vimeo": ("vimeo.com", "www.vimeo.com"),
    "X / Twitter": ("x.com", "www.x.com", "twitter.com", "www.twitter.com"),
}


st.markdown(
    f"""
    <style>
    :root {{ --tp-brand:{BRAND}; --tp-bg:{BG}; --tp-panel:{PANEL};
      --tp-panel2:{PANEL_2}; --tp-border:{BORDER}; --tp-text:{TEXT}; --tp-muted:{MUTED}; }}
    .stApp {{ background: radial-gradient(circle at 82% 0%, rgba(59,130,246,.07), transparent 30rem), var(--tp-bg); color:var(--tp-text); }}
    [data-testid="stHeader"] {{ background:rgba(7,9,13,.88); }}
    .block-container {{ max-width:1180px; padding-top:2rem; padding-bottom:4rem; }}
    .tp-topline {{ height:2px; background:linear-gradient(90deg,transparent,var(--tp-brand),transparent); margin-bottom:24px; }}
    .tp-eyebrow {{ color:var(--tp-brand); font-size:.72rem; font-weight:850; letter-spacing:.18em; text-transform:uppercase; }}
    .tp-title {{ color:var(--tp-text); font-size:clamp(2rem,4vw,3.5rem); line-height:1; font-weight:900; letter-spacing:-.045em; margin:.35rem 0 .8rem; }}
    .tp-copy {{ color:var(--tp-muted); max-width:760px; font-size:1rem; line-height:1.65; }}
    .tp-note {{ border:1px solid var(--tp-border); border-left:3px solid var(--tp-brand); border-radius:12px; background:var(--tp-panel); padding:14px 16px; color:var(--tp-muted); margin:22px 0; }}
    [data-testid="stForm"] {{ border:1px solid var(--tp-border); border-radius:16px; background:linear-gradient(145deg,var(--tp-panel2),var(--tp-panel)); padding:20px; }}
    div[data-testid="stButton"] > button, [data-testid="stFormSubmitButton"] button {{ border-radius:10px; font-weight:850; }}
    [data-testid="stFormSubmitButton"] button {{ background:linear-gradient(135deg,#ff4b55,#c9323d); color:white; border-color:#ff4b55; }}
    .tp-footer {{ color:#697688; text-align:center; font-size:.72rem; padding-top:28px; }}
    </style>
    """,
    unsafe_allow_html=True,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalized_url(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.username or parsed.password:
        return None
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or host.endswith(".local"):
        return None
    return value


def provider_for(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for provider, hosts in PROVIDER_HOSTS.items():
        if host in hosts or any(host.endswith(f".{allowed}") for allowed in hosts):
            return provider
    return "Other public link"


def safe_name(filename: str) -> str:
    base = Path(filename).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return cleaned[:160] or "video"


def database_url() -> str:
    return os.getenv("DATABASE_URL", "").strip()


def postgres_connect():
    import psycopg2

    url = database_url()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    return psycopg2.connect(url, connect_timeout=10)


def init_store() -> str:
    if database_url():
        with postgres_connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS research_submissions (
                    id UUID PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL,
                    submitter_name TEXT,
                    contact TEXT,
                    indicator_name TEXT,
                    creator_name TEXT,
                    market TEXT,
                    timeframe TEXT,
                    notes TEXT,
                    links JSONB NOT NULL DEFAULT '[]'::jsonb,
                    original_filename TEXT,
                    stored_filename TEXT,
                    content_type TEXT,
                    file_size BIGINT,
                    file_sha256 TEXT,
                    file_bytes BYTEA,
                    status TEXT NOT NULL DEFAULT 'PENDING_REVIEW',
                    consent_confirmed BOOLEAN NOT NULL DEFAULT FALSE
                )
                """
            )
        return "postgres"

    path = Path(os.getenv("TP_RESEARCH_SQLITE", "/tmp/tradingpulse_research.db"))
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS research_submissions (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                submitter_name TEXT, contact TEXT, indicator_name TEXT,
                creator_name TEXT, market TEXT, timeframe TEXT, notes TEXT,
                links TEXT NOT NULL, original_filename TEXT, stored_filename TEXT,
                content_type TEXT, file_size INTEGER, file_sha256 TEXT,
                file_bytes BLOB, status TEXT NOT NULL, consent_confirmed INTEGER NOT NULL
            )
            """
        )
    return "sqlite"


def save_submission(payload: dict, file_data: bytes | None) -> None:
    columns = (
        "id", "created_at", "submitter_name", "contact", "indicator_name",
        "creator_name", "market", "timeframe", "notes", "links",
        "original_filename", "stored_filename", "content_type", "file_size",
        "file_sha256", "file_bytes", "status", "consent_confirmed",
    )
    values = [payload.get(column) for column in columns]
    values[9] = json.dumps(values[9])
    values[15] = file_data

    mode = init_store()
    if mode == "postgres":
        placeholders = ",".join(["%s"] * len(columns))
        with postgres_connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO research_submissions ({','.join(columns)}) VALUES ({placeholders})",
                values,
            )
    else:
        placeholders = ",".join(["?"] * len(columns))
        values[1] = payload["created_at"].isoformat()
        values[-1] = int(bool(values[-1]))
        path = Path(os.getenv("TP_RESEARCH_SQLITE", "/tmp/tradingpulse_research.db"))
        with sqlite3.connect(path) as conn:
            conn.execute(
                f"INSERT INTO research_submissions ({','.join(columns)}) VALUES ({placeholders})",
                values,
            )


st.markdown('<div class="tp-topline"></div>', unsafe_allow_html=True)
st.markdown('<div class="tp-eyebrow">THE TRADING PULSE / RESEARCH INTAKE</div>', unsafe_allow_html=True)
st.markdown('<div class="tp-title">Share a Strategy or Indicator</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="tp-copy">Submit TikTok or Instagram videos, TradingView indicators, YouTube demonstrations, or your own video files for independent review. A submission is research material—not a verified trading signal.</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="tp-note"><b>What happens next:</b> Trading Pulse can evaluate whether the idea repaints, uses realistic data, adds measurable value, and can be implemented independently without copying proprietary code.</div>',
    unsafe_allow_html=True,
)

with st.form("research_intake", clear_on_submit=True):
    st.subheader("SUBMISSION DETAILS")
    left, right = st.columns(2)
    with left:
        submitter_name = st.text_input("Your name (optional)", max_chars=100)
        contact = st.text_input("Email or contact (optional)", max_chars=180)
        indicator_name = st.text_input("Indicator or strategy name", max_chars=160)
        creator_name = st.text_input("Creator name (optional)", max_chars=160)
    with right:
        market = st.selectbox("Market", ["Not specified", "GC / Gold", "CL / Crude Oil", "ES / S&P 500", "NQ / Nasdaq", "ETH", "Other"])
        timeframe = st.multiselect("Timeframes", ["15m", "30m", "1H", "4H", "Daily", "Weekly", "Other"])
        uploaded = st.file_uploader(
            f"Video file (optional, maximum {MAX_FILE_MB} MB)",
            type=sorted(ALLOWED_EXTENSIONS),
            accept_multiple_files=False,
        )

    links_text = st.text_area(
        "Video or indicator links",
        placeholder="Paste one public TikTok, Instagram, YouTube, TradingView, Vimeo, or X link per line",
        height=130,
        max_chars=5000,
    )
    notes = st.text_area(
        "What should we investigate?",
        placeholder="Example: Check whether the signals repaint and whether this could improve 15m supply-and-demand confirmation.",
        height=120,
        max_chars=3000,
    )
    rights = st.checkbox("I am authorized to share this material and understand that submission does not verify its trading claims.")
    submitted = st.form_submit_button("SUBMIT FOR REVIEW", type="primary", use_container_width=True)

if submitted:
    errors: list[str] = []
    raw_links = [line.strip() for line in links_text.splitlines() if line.strip()]
    if len(raw_links) > MAX_LINKS:
        errors.append(f"Submit no more than {MAX_LINKS} links at once.")

    links = []
    for raw in raw_links[:MAX_LINKS]:
        clean = normalized_url(raw)
        if not clean:
            errors.append(f"This is not a valid public web link: {raw[:100]}")
        else:
            links.append({"url": clean, "provider": provider_for(clean)})

    file_data = uploaded.getvalue() if uploaded is not None else None
    original_filename = safe_name(uploaded.name) if uploaded is not None else None
    extension = Path(original_filename or "").suffix.lower().lstrip(".")
    content_type = (uploaded.type or "application/octet-stream") if uploaded is not None else None

    if not links and not file_data:
        errors.append("Add at least one link or one video file.")
    if not rights:
        errors.append("Please confirm that you are authorized to share the material.")
    if file_data:
        if extension not in ALLOWED_EXTENSIONS or not content_type.startswith(ALLOWED_MIME_PREFIXES):
            errors.append("Only MP4, MOV, M4V, and WebM video files are accepted.")
        if len(file_data) > MAX_FILE_MB * 1024 * 1024:
            errors.append(f"The uploaded video exceeds the {MAX_FILE_MB} MB limit.")

    if errors:
        for error in errors:
            st.error(error)
    else:
        submission_id = str(uuid.uuid4())
        digest = hashlib.sha256(file_data).hexdigest() if file_data else None
        stored_filename = f"{submission_id}.{extension}" if file_data else None
        payload = {
            "id": submission_id,
            "created_at": utc_now(),
            "submitter_name": submitter_name.strip() or None,
            "contact": contact.strip() or None,
            "indicator_name": indicator_name.strip() or None,
            "creator_name": creator_name.strip() or None,
            "market": market,
            "timeframe": ", ".join(timeframe) if timeframe else None,
            "notes": notes.strip() or None,
            "links": links,
            "original_filename": original_filename,
            "stored_filename": stored_filename,
            "content_type": content_type,
            "file_size": len(file_data) if file_data else None,
            "file_sha256": digest,
            "status": "PENDING_REVIEW",
            "consent_confirmed": True,
        }
        try:
            save_submission(payload, file_data)
        except Exception:
            st.error("The submission could not be saved. Please try again shortly.")
        else:
            st.success("Submission received for review.")
            st.code(submission_id, language=None)
            st.caption("Save this private submission ID. Submitted material cannot change live trading rules automatically.")

st.divider()
st.markdown(
    '<div class="tp-footer">THE TRADING PULSE / EDUCATIONAL MARKET-ANALYSIS SOFTWARE / SUBMISSIONS ARE UNVERIFIED RESEARCH MATERIAL</div>',
    unsafe_allow_html=True,
)
