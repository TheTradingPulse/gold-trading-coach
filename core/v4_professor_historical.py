from __future__ import annotations
import re
from v4_historical_intelligence import HistoricalIntelligence

MONTHS={m.lower():i for i,m in enumerate(["January","February","March","April","May","June","July","August","September","October","November","December"],1)}
SYMS=("GC","SI","ES","NQ","YM","RTY","CL","NG")

def _symbol(q):
    m=re.search(r"\b(GC|SI|ES|NQ|YM|RTY|CL|NG)\b",q,re.I);return m.group(1).upper() if m else None

def parse_historical_question(question):
    q=" ".join((question or "").split());sym=_symbol(q)
    date=None
    m=re.search(r"\b("+"|".join(MONTHS)+r")\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(20\d{2}))?",q,re.I)
    if m:
        mon=MONTHS[m.group(1).lower()];day=int(m.group(2));year=int(m.group(3)) if m.group(3) else None
        date=f"{year:04d}-{mon:02d}-{day:02d}" if year else None
    tfm=re.search(r"\b(1m|15m|1h|4h|daily|1d)\b",q,re.I);tf=(tfm.group(1) if tfm else "15m").replace("1h","1H").replace("4h","4H").replace("daily","D").replace("1d","D")
    years_m=re.search(r"(?:past|last|over the past)\s+(\d+)\s+years?",q,re.I);years=int(years_m.group(1)) if years_m else 5
    if sym and date and any(w in q.lower() for w in ("chart","pull up","show me")):return {"intent":"chart","symbol":sym,"date":date,"timeframe":tf}
    if sym and date and any(w in q.lower() for w in ("similar","like this","like that","days like")):return {"intent":"similar_days","symbol":sym,"date":date,"timeframe":tf,"years":years}
    if sym and m and any(w in q.lower() for w in ("histor","past","last","usually","typically","how did","how has")):
        return {"intent":"date_history","symbol":sym,"month":MONTHS[m.group(1).lower()],"day":int(m.group(2)),"years":years,"through_year":int(m.group(3)) if m.group(3) else None}
    return {"intent":"unknown"}

def answer_historical_question(question,intelligence=None):
    intel=intelligence or HistoricalIntelligence();p=parse_historical_question(question);intent=p.pop("intent")
    if intent=="chart":return intel.chart(**p)
    if intent=="date_history":return intel.date_history(**p)
    if intent=="similar_days":return intel.similar_days(**p)
    return {"kind":"unsupported_historical_query","question":question,"reason":"No deterministic historical intent matched; no statistics fabricated."}
