"""Trading Pulse Professor research, telemetry, and verification warehouse.

Research is a candidate-knowledge pipeline, not automatic truth:
question -> local grounding -> optional OpenAI web research -> claims -> review queue.
MarketState remains authoritative for live trade facts.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from contextlib import contextmanager
import hashlib
import json
import os
import re
import sqlite3
import urllib.error
import urllib.request

ENGINE_VERSION = "3.4-PROF-RESEARCH-1"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "knowledge" / "professor_learning.db"
OPENAI_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = os.getenv("TRADINGPULSE_PROFESSOR_MODEL", "gpt-5.6-luna")

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS professor_questions(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 created_at TEXT NOT NULL,
 question TEXT NOT NULL,
 answer TEXT,
 symbol TEXT,
 timeframe TEXT,
 candidate_id TEXT,
 assessment TEXT,
 local_hit_count INTEGER NOT NULL DEFAULT 0,
 research_used INTEGER NOT NULL DEFAULT 0,
 research_status TEXT NOT NULL DEFAULT 'NOT_REQUESTED',
 model TEXT,
 latency_ms INTEGER,
 source_count INTEGER NOT NULL DEFAULT 0,
 claim_count INTEGER NOT NULL DEFAULT 0,
 user_rating INTEGER,
 user_correction TEXT
);
CREATE TABLE IF NOT EXISTS professor_sources(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 question_id INTEGER NOT NULL,
 url TEXT,
 title TEXT,
 domain TEXT,
 source_type TEXT NOT NULL DEFAULT 'WEB_RESEARCH',
 FOREIGN KEY(question_id) REFERENCES professor_questions(id)
);
CREATE TABLE IF NOT EXISTS professor_claims(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 question_id INTEGER NOT NULL,
 claim_hash TEXT NOT NULL,
 claim_text TEXT NOT NULL,
 claim_type TEXT NOT NULL DEFAULT 'RESEARCH_FACT',
 verification_status TEXT NOT NULL DEFAULT 'PENDING',
 support_count INTEGER NOT NULL DEFAULT 0,
 contradiction_count INTEGER NOT NULL DEFAULT 0,
 reviewer_note TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(claim_hash),
 FOREIGN KEY(question_id) REFERENCES professor_questions(id)
);
CREATE TABLE IF NOT EXISTS professor_claim_sources(
 claim_id INTEGER NOT NULL,
 source_id INTEGER NOT NULL,
 PRIMARY KEY(claim_id, source_id)
);
CREATE INDEX IF NOT EXISTS idx_prof_q_created ON professor_questions(created_at);
CREATE INDEX IF NOT EXISTS idx_prof_claim_status ON professor_claims(verification_status);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def _connect(db_path: Path | str = DEFAULT_DB):
    """Open a short-lived SQLite connection and always close it.

    Explicit close is required on Windows because a committed sqlite3 context
    manager does not close the connection; WAL/SHM handles can otherwise keep
    TemporaryDirectory databases locked during cleanup.
    """
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, timeout=10)
    try:
        con.row_factory = sqlite3.Row
        con.executescript(SCHEMA)
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def ensure_learning_db(db_path: Path | str = DEFAULT_DB) -> Path:
    with _connect(db_path):
        pass
    return Path(db_path)


def research_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def _extract_output_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"].strip()
    texts: list[str] = []
    for item in data.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) or []:
            if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                text = content.get("text")
                if isinstance(text, str):
                    texts.append(text)
    return "\n".join(texts).strip()


def _collect_web_sources(data: Any) -> list[dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    def walk(x: Any):
        if isinstance(x, dict):
            url = x.get("url")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                title = str(x.get("title") or x.get("name") or "Web source")
                domain = re.sub(r"^www\.", "", re.sub(r"^https?://", "", url).split("/")[0])
                found[url] = {"url": url, "title": title, "domain": domain}
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(data)
    return list(found.values())[:20]


def _claims_from_answer(answer: str) -> list[str]:
    """Conservative candidate extraction. Claims remain PENDING until reviewed."""
    text = re.sub(r"\s+", " ", answer or "").strip()
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    claims = []
    skip = ("trading pulse", "current setup", "current marketstate", "i cannot", "i don't", "watch / take")
    for s in sentences:
        s = s.strip(" -•\t")
        if len(s) < 45 or len(s) > 420:
            continue
        low = s.lower()
        if any(k in low for k in skip):
            continue
        if s not in claims:
            claims.append(s)
        if len(claims) >= 8:
            break
    return claims


def openai_web_research(question: str, live_context: dict[str, Any] | None = None, model: str | None = None) -> dict[str, Any]:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return {"ok": False, "status": "NO_API_KEY", "answer": "", "sources": [], "claims": [], "model": model or DEFAULT_MODEL}
    model = model or DEFAULT_MODEL
    live = json.dumps(live_context or {}, ensure_ascii=False, default=str)[:12000]
    instructions = """You are the research layer for The Trading Pulse AI Futures Professor.
Use web search when useful. Prefer primary and authoritative sources: exchanges (especially CME), CFTC/NFA, official economic/statistical agencies, regulator documentation, and reputable broker/platform documentation. Distinguish universal facts from trading opinions.
The supplied live MarketState is authoritative for current setup facts. Never invent or change entry, stop, targets, probabilities, readiness, confirmation, or execution permission.
Answer the user's question directly first. Then use these headings when relevant: LIVE TRADE ANALYSIS, TAUGHT/GROUNDED KNOWLEDGE, RESEARCH, PROFESSOR CONCLUSION. If evidence is uncertain or sources conflict, say so. Do not claim that researched material has been learned or verified; it enters a pending review queue."""
    payload = {
        "model": model,
        "tools": [{"type": "web_search"}],
        "input": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": f"QUESTION:\n{question}\n\nCANONICAL LIVE CONTEXT:\n{live}"},
        ],
    }
    req = urllib.request.Request(
        OPENAI_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        answer = _extract_output_text(data)
        sources = _collect_web_sources(data)
        return {"ok": bool(answer), "status": "COMPLETE" if answer else "EMPTY", "answer": answer, "sources": sources, "claims": _claims_from_answer(answer), "model": model}
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8")[:1200]
        except Exception:
            detail = str(exc)
        return {"ok": False, "status": f"HTTP_{exc.code}", "error": detail, "answer": "", "sources": [], "claims": [], "model": model}
    except Exception as exc:
        return {"ok": False, "status": "ERROR", "error": str(exc), "answer": "", "sources": [], "claims": [], "model": model}


def record_exchange(question: str, answer: str, context: dict[str, Any] | None, local_hit_count: int, research: dict[str, Any] | None, latency_ms: int | None = None, db_path: Path | str = DEFAULT_DB) -> int:
    ctx = context or {}
    selected = ctx.get("selected_setup", {}) if isinstance(ctx, dict) else {}
    research = research or {}
    now = _now()
    sources = research.get("sources") or []
    claims = research.get("claims") or []
    with _connect(db_path) as con:
        cur = con.execute(
            """INSERT INTO professor_questions(created_at,question,answer,symbol,timeframe,candidate_id,assessment,local_hit_count,research_used,research_status,model,latency_ms,source_count,claim_count)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (now, question, answer, selected.get("symbol") or ctx.get("symbol"), selected.get("timeframe"), selected.get("candidate_id"), ctx.get("professor_assessment"), int(local_hit_count), int(bool(research.get("ok"))), research.get("status", "NOT_REQUESTED"), research.get("model"), latency_ms, len(sources), len(claims)),
        )
        qid = int(cur.lastrowid)
        source_ids = []
        for s in sources:
            sc = con.execute("INSERT INTO professor_sources(question_id,url,title,domain,source_type) VALUES(?,?,?,?,?)", (qid, s.get("url"), s.get("title"), s.get("domain"), "WEB_RESEARCH"))
            source_ids.append(int(sc.lastrowid))
        for claim in claims:
            norm = re.sub(r"\s+", " ", claim.strip()).lower()
            h = hashlib.sha256(norm.encode("utf-8")).hexdigest()
            con.execute("""INSERT OR IGNORE INTO professor_claims(question_id,claim_hash,claim_text,claim_type,verification_status,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?)""", (qid, h, claim, "RESEARCH_FACT", "PENDING", now, now))
            row = con.execute("SELECT id FROM professor_claims WHERE claim_hash=?", (h,)).fetchone()
            if row:
                for sid in source_ids:
                    con.execute("INSERT OR IGNORE INTO professor_claim_sources(claim_id,source_id) VALUES(?,?)", (int(row[0]), sid))
    return qid


def rate_question(question_id: int, rating: int | None = None, correction: str | None = None, db_path: Path | str = DEFAULT_DB) -> None:
    with _connect(db_path) as con:
        con.execute("UPDATE professor_questions SET user_rating=?, user_correction=? WHERE id=?", (rating, correction, int(question_id)))


def set_claim_status(claim_id: int, status: str, note: str = "", db_path: Path | str = DEFAULT_DB) -> None:
    status = str(status).upper()
    if status not in {"PENDING", "CORROBORATED", "VERIFIED", "CONFLICTED", "REJECTED", "SUPERSEDED"}:
        raise ValueError("Invalid verification status")
    with _connect(db_path) as con:
        con.execute("UPDATE professor_claims SET verification_status=?, reviewer_note=?, updated_at=? WHERE id=?", (status, note, _now(), int(claim_id)))


def metrics(db_path: Path | str = DEFAULT_DB) -> dict[str, Any]:
    with _connect(db_path) as con:
        total = con.execute("SELECT count(*) FROM professor_questions").fetchone()[0]
        researched = con.execute("SELECT count(*) FROM professor_questions WHERE research_used=1").fetchone()[0]
        avg_sources = con.execute("SELECT avg(source_count) FROM professor_questions").fetchone()[0] or 0
        claims = dict(con.execute("SELECT verification_status,count(*) FROM professor_claims GROUP BY verification_status").fetchall())
        ratings = con.execute("SELECT avg(user_rating) FROM professor_questions WHERE user_rating IS NOT NULL").fetchone()[0]
        gaps = con.execute("SELECT count(*) FROM professor_questions WHERE local_hit_count=0").fetchone()[0]
        return {"questions": int(total), "researched": int(researched), "research_pct": (100.0*researched/total if total else 0.0), "knowledge_gaps": int(gaps), "avg_sources": float(avg_sources), "claims": claims, "avg_rating": ratings}


def recent_questions(limit: int = 20, db_path: Path | str = DEFAULT_DB) -> list[dict[str, Any]]:
    with _connect(db_path) as con:
        rows = con.execute("SELECT id,created_at,question,symbol,timeframe,local_hit_count,research_status,source_count,claim_count,user_rating FROM professor_questions ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
        return [dict(r) for r in rows]


def pending_claims(limit: int = 30, db_path: Path | str = DEFAULT_DB) -> list[dict[str, Any]]:
    with _connect(db_path) as con:
        rows = con.execute("""SELECT c.id,c.claim_text,c.verification_status,c.created_at,count(cs.source_id) AS sources
                              FROM professor_claims c LEFT JOIN professor_claim_sources cs ON cs.claim_id=c.id
                              WHERE c.verification_status IN ('PENDING','CORROBORATED','CONFLICTED')
                              GROUP BY c.id ORDER BY c.id DESC LIMIT ?""", (int(limit),)).fetchall()
        return [dict(r) for r in rows]
