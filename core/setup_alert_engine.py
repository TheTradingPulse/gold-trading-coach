"""
Trading Pulse V3.0D - deterministic cross-market setup alert/radar engine.

Alerts are analysis events, not orders. Yahoo/reference data can surface a
setup for review but can never make it execution/broker eligible.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Iterable, Mapping, Any

ENGINE_VERSION = "3.0D"
ELITE_SCORE = 9.0
ALERTABLE_LIFECYCLES = {"APPROACHING", "IN_ZONE", "QUALIFIED"}

@dataclass(frozen=True)
class SetupAlert:
    alert_id: str
    symbol: str
    score: float
    timeframe: str
    side: str
    lifecycle: str
    candidate_id: str
    message: str
    execution_eligible: bool = False

    def to_dict(self):
        return asdict(self)

def build_alerts(scan_result: Mapping[str, Any], minimum_score: float = ELITE_SCORE) -> list[SetupAlert]:
    alerts = []
    for row in scan_result.get("setups", []) or []:
        score = float(row.get("score", 0.0) or 0.0)
        lifecycle = str(row.get("lifecycle", "") or "").upper()
        if score < float(minimum_score) or lifecycle not in ALERTABLE_LIFECYCLES:
            continue
        symbol = str(row.get("symbol", "") or "").upper()
        cid = str(row.get("candidate_id", "") or "")
        tf = str(row.get("timeframe", "") or "")
        side = str(row.get("side", "") or "")
        aid = f"{symbol}:{cid}:{lifecycle}"
        alerts.append(SetupAlert(
            alert_id=aid,
            symbol=symbol,
            score=score,
            timeframe=tf,
            side=side,
            lifecycle=lifecycle,
            candidate_id=cid,
            message=f"{symbol} {score:.1f}/10 {tf} {side} {lifecycle.replace('_',' ')}",
            execution_eligible=False,
        ))
    alerts.sort(key=lambda a: (-a.score, a.symbol, a.timeframe))
    return alerts

def new_alerts(current: Iterable[SetupAlert], previously_seen_ids: Iterable[str]) -> list[SetupAlert]:
    seen = set(previously_seen_ids or [])
    return [a for a in current if a.alert_id not in seen]

def radar_summary(alerts: Iterable[SetupAlert]) -> dict:
    rows = list(alerts)
    return {
        "count": len(rows),
        "symbols": sorted({a.symbol for a in rows}),
        "top": rows[0].to_dict() if rows else None,
        "alerts": [a.to_dict() for a in rows],
    }
