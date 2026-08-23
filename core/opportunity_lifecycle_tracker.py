"""Trading Pulse V3.4E - opportunity lifecycle + local evidence ledger.

This is intentionally separate from the trade journal. It observes WATCH/ELITE
opportunities and records state transitions in a local JSONL evidence ledger.
It never places orders, never creates journal trades, and never touches production.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

ENGINE_VERSION = "3.4E"
DEFAULT_LEDGER = Path("research_data/evidence/opportunity_lifecycle.jsonl")
TERMINAL = {"TRIGGERED", "INVALIDATED", "EXPIRED", "RESOLVED"}

@dataclass(frozen=True)
class OpportunityObservation:
    observed_at: str
    symbol: str
    candidate_id: str
    tier: str
    stage: str
    timeframe: str
    direction: str
    setup_score: float
    composite_score: float
    lifecycle: str
    zone_quality: float
    freshness: float
    retests: int
    projected_rr: float | None
    mtf_aligned: int
    mtf_total: int
    confirmations: int
    distance_percent: float
    engine_version: str = ENGINE_VERSION
    def to_dict(self): return asdict(self)

def _now():
    return datetime.now(timezone.utc).isoformat()

def stage_for(opportunity: Any) -> str:
    c = opportunity.candidate
    lifecycle = str(getattr(c, "lifecycle", "") or "").upper()
    if lifecycle == "QUALIFIED":
        return "ARMED"
    if lifecycle == "IN_ZONE":
        return "ARMED"
    if lifecycle == "APPROACHING":
        return "APPROACHING" if opportunity.tier == "ELITE" else "WATCHING"
    return "DISCOVERED"

def observation_from_opportunity(opportunity: Any, observed_at: str | None = None):
    c = opportunity.candidate
    return OpportunityObservation(
        observed_at=observed_at or _now(),
        symbol=str(opportunity.symbol),
        candidate_id=str(c.candidate_id),
        tier=str(opportunity.tier),
        stage=stage_for(opportunity),
        timeframe=str(c.timeframe),
        direction=str(opportunity.direction),
        setup_score=float(c.setup_score),
        composite_score=float(opportunity.composite_score),
        lifecycle=str(c.lifecycle),
        zone_quality=float(c.zone_quality_score),
        freshness=float(c.freshness_score),
        retests=int(c.retest_count),
        projected_rr=None if c.projected_rr is None else float(c.projected_rr),
        mtf_aligned=int(opportunity.mtf_aligned),
        mtf_total=int(opportunity.mtf_total),
        confirmations=int(opportunity.confirmation_count),
        distance_percent=float(c.distance_percent),
    )

def load_latest(path=DEFAULT_LEDGER):
    p = Path(path)
    latest = {}
    if not p.exists():
        return latest
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            latest[(row["symbol"], row["candidate_id"])] = row
        except Exception:
            continue
    return latest

def append_snapshot(elite, watch, path=DEFAULT_LEDGER, observed_at=None):
    """Append only changed/new observations. Returns a summary; no journal writes."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    latest = load_latest(p)
    rows = [observation_from_opportunity(o, observed_at).to_dict() for o in list(elite)+list(watch)]
    written = 0
    transitions = []
    with p.open("a", encoding="utf-8") as fh:
        for row in rows:
            key = (row["symbol"], row["candidate_id"])
            prior = latest.get(key)
            signature = (row["tier"], row["stage"], row["lifecycle"], row["confirmations"])
            oldsig = None if prior is None else (
                prior.get("tier"), prior.get("stage"), prior.get("lifecycle"), prior.get("confirmations")
            )
            if signature == oldsig:
                continue
            row["previous_stage"] = None if prior is None else prior.get("stage")
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
            written += 1
            transitions.append({
                "symbol": row["symbol"], "candidate_id": row["candidate_id"],
                "from": row["previous_stage"], "to": row["stage"], "tier": row["tier"]
            })
    return {"observed": len(rows), "written": written, "transitions": transitions, "path": str(p)}

def evidence_summary(path=DEFAULT_LEDGER):
    p = Path(path)
    if not p.exists():
        return {"rows":0,"candidates":0,"markets":{},"stages":{}}
    rows=[]
    for line in p.read_text(encoding="utf-8").splitlines():
        try: rows.append(json.loads(line))
        except Exception: pass
    keys={(r.get("symbol"),r.get("candidate_id")) for r in rows}
    markets={}; stages={}
    for r in rows:
        markets[r.get("symbol","?")]=markets.get(r.get("symbol","?"),0)+1
        stages[r.get("stage","?")]=stages.get(r.get("stage","?"),0)+1
    return {"rows":len(rows),"candidates":len(keys),"markets":markets,"stages":stages}
