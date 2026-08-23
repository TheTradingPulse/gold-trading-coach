"""Trading Pulse V3.4 Pass 5 - grounded Professor + Beginner Academy.

The Professor is deliberately deterministic at this stage:
- live-market facts come only from canonical MarketState.professor_payload()
- educational definitions are retrieved from the FuturesProf SQLite corpus
- no prices, probabilities, zones, entries, stops, or targets are invented
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import re
import sqlite3
import time

from professor_learning import (
    ensure_learning_db, metrics as professor_metrics, openai_web_research,
    pending_claims, rate_question, recent_questions, record_exchange,
    research_available, set_claim_status,
)

ENGINE_VERSION="3.4-P5"
DEFAULT_DB=Path(__file__).resolve().parents[1]/"knowledge"/"futuresprof.db"

ACADEMY = [
 {"id":1,"title":"Futures in Plain English","goal":"Understand what a futures contract is and why leverage makes risk control essential.",
  "body":"A futures contract is a standardized agreement traded on an exchange. Futures let traders take LONG or SHORT exposure without owning the underlying asset. Because futures are leveraged, small market moves can create meaningful gains or losses.",
  "check":"Before trading, identify the contract, tick size/value, and the maximum amount you are willing to lose."},
 {"id":2,"title":"Set Up TradingView","goal":"Create the charting workspace you will use for practice.",
  "body":"Create or sign in to a TradingView account, open a chart, search for the futures symbol you want to study, and become comfortable changing chart timeframes. Trading Pulse uses multiple timeframes, so do not judge a setup from one chart alone.",
  "check":"You can open a futures chart and switch among 1m, 5m, 15m, 1H, 4H, and Daily."},
 {"id":3,"title":"Turn On Paper Trading","goal":"Practice execution without risking real money.",
  "body":"In TradingView, open the trading panel and connect Paper Trading. Use the simulated account while learning. Confirm the selected symbol and quantity before submitting any simulated order.",
  "check":"Your order ticket clearly shows Paper Trading, not a live brokerage connection."},
 {"id":4,"title":"LONG, SHORT, Entry, Stop, Target","goal":"Understand the four pieces of every trade plan.",
  "body":"LONG means the plan benefits if price rises; SHORT means it benefits if price falls. Entry is where the position begins. Stop is the predefined invalidation/risk level. Target is where the plan intends to take profit.",
  "check":"You can point to direction, entry, stop, and target before clicking Buy or Sell."},
 {"id":5,"title":"Risk and R","goal":"Think in risk units instead of dollars won.",
  "body":"One R is the amount initially risked between entry and stop. A 2R target seeks twice that initial risk. Trading Pulse rejects preview opportunities below its current minimum R:R gate; this is a system rule, not a guarantee of profit.",
  "check":"Never move a paper-trade stop farther away merely to avoid taking a loss."},
 {"id":6,"title":"Read a Trading Pulse Opportunity","goal":"Understand why a setup is WATCH or ELITE.",
  "body":"Trading Pulse combines setup score with structural timeframe, lifecycle, zone quality, freshness, retests, projected R:R, and multi-timeframe alignment. 1m and 5m are confirmation timeframes; structural opportunities originate from 15m, 1H, 4H, or Daily.",
  "check":"Explain why a lower-timeframe confirmation is evidence for an idea rather than a separate Elite idea."},
 {"id":7,"title":"Place Your First Paper Trade","goal":"Translate the deterministic Trading Pulse plan into a simulated order.",
  "body":"Only practice a setup when Trading Pulse exposes a deterministic trade plan. Match the symbol and direction, enter the displayed entry, use the displayed stop, and use the displayed target. If Trading Pulse has no validated levels, do not invent them.",
  "check":"Before submitting, read symbol, direction, quantity, entry, stop, and target back to yourself."},
 {"id":8,"title":"Manage and Review","goal":"Learn from process rather than one outcome.",
  "body":"After entry, follow the predefined paper plan. Record whether the setup triggered, stopped, reached target, expired, or invalidated. Review the setup context and execution afterward. A winning trade can still be poorly executed; a losing trade can still follow the process correctly.",
  "check":"Your review separates decision quality from the trade's financial outcome."},
]

@dataclass(frozen=True)
class GroundingHit:
    text:str
    source_domain:str
    page_title:str
    quality:int

def academy_lessons(): return list(ACADEMY)

def _tokens(q:str):
    return [x for x in re.findall(r"[a-zA-Z0-9]+",q.lower()) if len(x)>=3][:8]

def search_knowledge(question:str, db_path:Path|str=DEFAULT_DB, limit:int=4):
    p=Path(db_path)
    if not p.exists(): return []
    toks=_tokens(question)
    if not toks:return []
    clauses=" OR ".join(["lower(normalized_text) LIKE ?" for _ in toks])
    params=[f"%{t}%" for t in toks]+[int(limit)]
    sql=f"""SELECT passage_text,coalesce(source_domain,''),coalesce(page_title,''),quality_score
             FROM knowledge_passages
             WHERE status='ready' AND ({clauses})
             ORDER BY quality_score DESC, word_count ASC LIMIT ?"""
    try:
        with sqlite3.connect(p) as con:
            return [GroundingHit(str(a),str(b),str(c),int(d or 0)) for a,b,c,d in con.execute(sql,params)]
    except Exception:
        return []

def _market_summary(payload:dict[str,Any]):
    setup=payload.get("setup",{}) if isinstance(payload,dict) else {}
    confirmation=payload.get("confirmation",{}) if isinstance(payload,dict) else {}
    trade=payload.get("trade_plan",{}) if isinstance(payload,dict) else {}
    symbol=payload.get("symbol") or payload.get("root_symbol") or "--"
    lines=[
      f"Current canonical symbol: {symbol}.",
      f"Setup state: {setup.get('state','--')}; direction: {setup.get('direction') or '--'}.",
    ]
    missing=confirmation.get("missing_conditions") or []
    if missing: lines.append("Still required: "+", ".join(map(str,missing[:3]))+".")
    if trade:
        # We deliberately quote only values already present in the canonical payload.
        vals=[]
        for key in ("entry","stop"):
            if trade.get(key) is not None: vals.append(f"{key}={trade.get(key)}")
        if vals: lines.append("Canonical trade plan: "+", ".join(vals)+".")
    return " ".join(lines)

def answer_question(question:str, professor_payload:dict[str,Any], db_path:Path|str=DEFAULT_DB, research_mode:bool=True):
    """Answer from canonical live facts + local corpus + optional web research.

    Web research never becomes verified knowledge automatically. Candidate claims are
    written to professor_learning.db as PENDING for later review.
    """
    started=time.perf_counter()
    q=(question or "").strip()
    if not q:
        return {"answer":"Ask a question about the current market or a futures concept.","sources":[],"research_status":"EMPTY_QUESTION"}

    low=q.lower()
    market_words=("this setup","this trade","current","why are we","entry","stop","target","elite","watch","mtf","market","timeframe","confirmation")
    live_pieces=[]
    if any(w in low for w in market_words):
        live_pieces.append(_market_summary(professor_payload))

    hits=search_knowledge(q,db_path)
    local_sources=[{"domain":h.source_domain,"title":h.page_title,"quality":h.quality,"source_type":"FUTURESPROF"} for h in hits]

    # Bootstrap mode: when configured, research the open web for a richer answer.
    research={"ok":False,"status":"NOT_REQUESTED","answer":"","sources":[],"claims":[],"model":None}
    if research_mode:
        research=openai_web_research(q, professor_payload)

    if research.get("ok"):
        answer=str(research.get("answer") or "").strip()
        if live_pieces and "LIVE TRADE ANALYSIS" not in answer.upper():
            answer="LIVE TRADE ANALYSIS\n"+" ".join(live_pieces)+"\n\nRESEARCH + PROFESSOR CONCLUSION\n"+answer
    else:
        pieces=[]
        if live_pieces:
            pieces.extend(live_pieces)
            pieces.append("Those live-market facts come from the same canonical MarketState displayed on the dashboard.")
        if hits:
            h=hits[0]
            clean=" ".join(h.text.split())
            pieces.append("TAUGHT / GROUNDED KNOWLEDGE\n"+clean[:900]+("..." if len(clean)>900 else ""))
        if not pieces:
            pieces.append("I do not have enough grounded information to answer that safely yet. Research Mode can expand this answer after an OpenAI API key is configured.")
        if research_mode and research.get("status") == "NO_API_KEY":
            pieces.append("RESEARCH STATUS\nResearch Mode is installed but OPENAI_API_KEY is not configured on this machine yet.")
        elif research_mode and research.get("status") not in {"NOT_REQUESTED","NO_API_KEY"}:
            pieces.append("RESEARCH STATUS\nExternal research was attempted but did not complete: "+str(research.get("status")))
        answer="\n\n".join(pieces)

    all_sources=local_sources+[{**x,"quality":"WEB","source_type":"WEB_RESEARCH"} for x in (research.get("sources") or [])]
    elapsed=int((time.perf_counter()-started)*1000)
    qid=record_exchange(q,answer,professor_payload,len(hits),research,elapsed)
    return {
        "answer":answer, "sources":all_sources, "engine_version":ENGINE_VERSION,
        "question_id":qid, "research_status":research.get("status"),
        "research_used":bool(research.get("ok")), "local_hit_count":len(hits),
        "pending_claims":len(research.get("claims") or []),
    }


def get_professor_metrics():
    return professor_metrics()

def get_recent_professor_questions(limit:int=20):
    return recent_questions(limit)

def get_pending_professor_claims(limit:int=30):
    return pending_claims(limit)

def professor_research_available():
    return research_available()

def rate_professor_answer(question_id:int, rating:int|None=None, correction:str|None=None):
    return rate_question(question_id,rating,correction)

def review_professor_claim(claim_id:int,status:str,note:str=""):
    return set_claim_status(claim_id,status,note)

ensure_learning_db()
