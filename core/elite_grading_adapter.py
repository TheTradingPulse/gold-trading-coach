"""Small, read-only adapter for the promoted V4 Elite grading rules.

It does not fetch data, change MarketState, alter trade plans, or run backtests.
Raw structure score alone can never create Elite.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "research_data" / "v4" / "temporal_regime_sniper" / "frozen_temporal_rules.json"
REPORT_PATH = ROOT / "research_data" / "v4" / "temporal_regime_sniper" / "temporal_regime_report.json"


def _float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rr_bucket(value: Any) -> str:
    rr = _float(value)
    if rr is None:
        return "UNKNOWN"
    if rr < 2:
        return "<2"
    if rr < 3:
        return "2-3"
    if rr < 4:
        return "3-4"
    if rr < 5:
        return "4-5"
    return "5+"


def _session() -> str:
    hour = datetime.now(timezone.utc).hour
    if hour < 6:
        return "UTC_00_06"
    if hour < 12:
        return "UTC_06_12"
    if hour < 18:
        return "UTC_12_18"
    return "UTC_18_24"


@lru_cache(maxsize=1)
def _policy() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    promotion = dict(report.get("promotion") or {})
    if promotion.get("elite") is not True:
        return [], promotion
    return list(rules.get("elite") or []), promotion


def grade_elite_candidate(candidate: Any, market_state: Any, symbol: str) -> dict[str, Any]:
    raw = _float(getattr(candidate, "setup_score", 0.0), 0.0) or 0.0
    structure_score = raw / 10.0 if raw > 10 else raw
    base = {
        "tier": "RESEARCH",
        "structure_score10": round(structure_score, 2),
        "confidence10": None,
        "sample": 0,
        "hit_3r_pct": None,
        "hit_5r_pct": None,
        "reason": "No promoted frozen Elite rule matches this setup.",
    }
    if not RULES_PATH.exists() or not REPORT_PATH.exists():
        base["tier"] = "INSUFFICIENT EVIDENCE"
        base["reason"] = "Promoted V4 grading artifacts are missing."
        return base

    try:
        rules, promotion = _policy()
    except Exception as exc:
        base["tier"] = "INSUFFICIENT EVIDENCE"
        base["reason"] = f"V4 grading artifacts could not be read: {exc}"
        return base
    if not rules or promotion.get("grand_slam") is not False:
        base["tier"] = "INSUFFICIENT EVIDENCE"
        base["reason"] = "V4 promotion state is not safe for live grading."
        return base

    zone_type = str(getattr(candidate, "zone_type", "unknown")).lower()
    trends = dict(getattr(market_state, "trends", {}) or {})
    values = {
        "symbol": str(symbol).upper(),
        "setup_type": zone_type,
        "direction": "LONG" if zone_type == "demand" else "SHORT",
        "rr_bucket": _rr_bucket(getattr(candidate, "projected_rr", None)),
        "session": _session(),
        "trend_1h": str(trends.get("1H", "UNKNOWN") or "UNKNOWN").lower(),
        "trend_4h": str(trends.get("4H", "UNKNOWN") or "UNKNOWN").lower(),
        "volatility": "UNKNOWN",
    }
    matches = [
        rule for rule in rules
        if all(str(values.get(feature, "UNKNOWN")) == str(value)
               for feature, value in zip(rule.get("features", []), rule.get("values", [])))
    ]
    if not matches:
        return base

    rule = max(
        matches,
        key=lambda item: (
            _float((item.get("calibration") or {}).get("w3"), 0.0) or 0.0,
            _float((item.get("calibration") or {}).get("w5"), 0.0) or 0.0,
        ),
    )
    stats = rule.get("calibration") or rule.get("stats") or {}
    w3 = _float(stats.get("w3"), 0.0) or 0.0
    return {
        # The promoted rule is a strong historical-context match, but the current
        # evidence warehouse does not yet prove mutually exclusive first-touch
        # ordering for these very tight stops.  Do not issue an Elite star until
        # execution viability is revalidated on intraday timestamps.
        "tier": "EVIDENCE MATCH",
        "execution_status": "UNVERIFIED",
        "structure_score10": round(structure_score, 2),
        "confidence10": round(w3 * 10.0, 2),
        "sample": int(stats.get("triggered") or 0),
        "hit_3r_pct": round((_float(stats.get("p3"), 0.0) or 0.0) * 100.0, 1),
        "hit_5r_pct": round((_float(stats.get("p5"), 0.0) or 0.0) * 100.0, 1),
        "reason": "Matches a promoted frozen temporal-regime rule; first-touch stop/target ordering is not yet verified.",
    }
