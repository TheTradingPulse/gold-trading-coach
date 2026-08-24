"""Production-facing V4 evidence adapter for Trading Pulse.

This module is deliberately fail-closed.  A raw structural score can describe a
candidate, but it can never create an evidence tier.  ELITE/WATCH classifications
require a readable calibration artifact and a complete V4 release-health bundle.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from v4_backtest_intelligence import evidence_metrics, research_artifacts
from v4_release_health import release_health


PROJECT_ROOT = Path(__file__).resolve().parents[1]
V4_ROOT = PROJECT_ROOT / "research_data" / "v4"
CALIBRATION_CANDIDATES = (
    V4_ROOT / "v4_calibration.json",
    PROJECT_ROOT / "research_data" / "v4_calibration.json",
)
CONTEXT_EVIDENCE = V4_ROOT / "context_evidence_v4.db"
COMPACT_EVIDENCE = V4_ROOT / "v4_live_evidence_bundle.json"
TEMPORAL_RULES = V4_ROOT / "temporal_regime_sniper" / "frozen_temporal_rules.json"
TEMPORAL_REPORT = V4_ROOT / "temporal_regime_sniper" / "temporal_regime_report.json"


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


def _utc_session() -> str:
    hour = datetime.now(timezone.utc).hour
    if hour < 6:
        return "UTC_00_06"
    if hour < 12:
        return "UTC_06_12"
    if hour < 18:
        return "UTC_12_18"
    return "UTC_18_24"


def _candidate_payload(candidate: Any, symbol: str, market_state: Any = None) -> dict[str, Any]:
    zone_type = str(getattr(candidate, "zone_type", "unknown")).lower()
    direction = "LONG" if zone_type == "demand" else "SHORT"
    raw = _float(getattr(candidate, "setup_score", 0.0), 0.0) or 0.0
    trends = dict(getattr(market_state, "trends", {}) or {})
    rr = _float(getattr(candidate, "projected_rr", None))
    return {
        "symbol": str(symbol).upper(),
        "setup_type": zone_type,
        "zone_type": zone_type,
        "direction": direction,
        "score10": raw / 10.0 if raw > 10 else raw,
        "setup_score": raw,
        "timeframe": str(getattr(candidate, "timeframe", "")),
        "lifecycle": str(getattr(candidate, "lifecycle", "")),
        "zone_quality_score": _float(getattr(candidate, "zone_quality_score", 0.0), 0.0),
        "freshness_score": _float(getattr(candidate, "freshness_score", 0.0), 0.0),
        "retest_count": int(_float(getattr(candidate, "retest_count", 0), 0) or 0),
        "projected_rr": rr,
        "rr_bucket": _rr_bucket(rr),
        "session": _utc_session(),
        "trend_1h": str(trends.get("1H", "UNKNOWN") or "UNKNOWN").lower(),
        "trend_4h": str(trends.get("4H", "UNKNOWN") or "UNKNOWN").lower(),
        "volatility": "UNKNOWN",
    }


def calibration_path() -> Path | None:
    return next((path for path in CALIBRATION_CANDIDATES if path.exists()), None)


@lru_cache(maxsize=4)
def _read_json(path_text: str) -> dict[str, Any]:
    path = Path(path_text)
    return json.loads(path.read_text(encoding="utf-8"))


def _compact_evidence() -> dict[str, Any] | None:
    if not COMPACT_EVIDENCE.exists():
        return None
    try:
        bundle = _read_json(str(COMPACT_EVIDENCE))
        evidence = dict(bundle.get("evidence") or {})
        evidence["compact"] = True
        evidence["path"] = str(COMPACT_EVIDENCE)
        return evidence
    except Exception:
        return None


def _temporal_promotion() -> dict[str, Any]:
    if not TEMPORAL_REPORT.exists():
        return {"elite": False, "grand_slam": False, "status": "MISSING"}
    try:
        return dict(_read_json(str(TEMPORAL_REPORT)).get("promotion") or {})
    except Exception:
        return {"elite": False, "grand_slam": False, "status": "INVALID"}


def v4_system_status() -> dict[str, Any]:
    calibration = calibration_path()
    health = release_health(PROJECT_ROOT)
    evidence = evidence_metrics(CONTEXT_EVIDENCE) if CONTEXT_EVIDENCE.exists() else (_compact_evidence() or {"available": False, "reason": "evidence unavailable"})
    promotion = _temporal_promotion()
    rules_available = TEMPORAL_RULES.exists()
    return {
        "ready": bool(health.get("ready") and evidence.get("available") and rules_available and promotion.get("elite")),
        "calibration_available": calibration is not None,
        "calibration_path": str(calibration) if calibration else None,
        "release_health": health,
        "evidence": evidence,
        "temporal_rules_available": rules_available,
        "promotion": promotion,
        "artifacts": research_artifacts(V4_ROOT),
    }


def classify_live_candidate(candidate: Any, symbol: str, market_state: Any = None) -> dict[str, Any]:
    """Return the authoritative live research tier for one canonical candidate."""
    payload = _candidate_payload(candidate, symbol, market_state)
    structural_score = round(float(payload["score10"]), 2)
    status = v4_system_status()
    base = {
        "tier": "INSUFFICIENT EVIDENCE",
        "structure_score10": structural_score,
        "evidence_score10": None,
        "triggered_sample": 0,
        "hit_3r_pct": None,
        "hit_5r_pct": None,
        "release_ready": bool(status["ready"]),
        "reason": "V4 evidence bundle is incomplete.",
        "raw": None,
    }
    if not status["ready"]:
        base["reason"] = "Classification blocked until every V4 release-health and promotion check passes."
        return base
    try:
        frozen = _read_json(str(TEMPORAL_RULES))
        rules = list(frozen.get("elite") or [])
    except Exception as exc:
        base["reason"] = f"Promoted frozen rules could not be read: {exc}"
        return base
    matches = [
        rule for rule in rules
        if all(str(payload.get(feature, "UNKNOWN")) == str(value)
               for feature, value in zip(rule.get("features", []), rule.get("values", [])))
    ]
    if not matches:
        base["tier"] = "RESEARCH"
        base["reason"] = "No promoted temporal-regime Elite rule matches the current candidate context."
        return base
    matched = max(
        matches,
        key=lambda rule: (
            _float((rule.get("calibration") or {}).get("w3"), 0.0) or 0.0,
            _float((rule.get("calibration") or {}).get("w5"), 0.0) or 0.0,
            _float(rule.get("quality"), 0.0) or 0.0,
        ),
    )
    stats = matched.get("calibration") or matched.get("stats") or {}
    w3 = _float(stats.get("w3"), 0.0) or 0.0
    base.update({
        # A promoted historical rule is not enough for a live star.  The
        # canonical execution adapter must still prove first-touch ordering.
        "tier": "EVIDENCE MATCH",
        "execution_status": "UNVERIFIED",
        "evidence_score10": round(w3 * 10.0, 2),
        "triggered_sample": int(stats.get("triggered") or 0),
        "hit_3r_pct": round((_float(stats.get("p3"), 0.0) or 0.0) * 100.0, 2),
        "hit_5r_pct": round((_float(stats.get("p5"), 0.0) or 0.0) * 100.0, 2),
        "raw": matched,
        "reason": "Candidate matches a promoted frozen temporal-regime rule; live Elite remains blocked until canonical first-touch execution verification.",
    })
    return base


def evidence_lab_snapshot(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    status = v4_system_status()
    if CONTEXT_EVIDENCE.exists():
        metrics = evidence_metrics(CONTEXT_EVIDENCE, filters or {})
    else:
        metrics = _compact_evidence() or {"available": False, "reason": "compact evidence bundle not found"}
    reports = {}
    report_paths = (
        V4_ROOT / "v4_oos_validation.json",
        V4_ROOT / "v4_walkforward_report.json",
        V4_ROOT / "temporal_regime_sniper" / "temporal_regime_report.json",
        V4_ROOT / "elite_65_hardening" / "elite_65_hardening_report.json",
        V4_ROOT / "grandslam_oos" / "grandslam_oos_report.json",
    )
    for path in report_paths:
        name = str(path.relative_to(V4_ROOT)).replace("\\", "/")
        if path.exists():
            try:
                reports[name] = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                reports[name] = {"error": str(exc)}
    return {"status": status, "metrics": metrics, "reports": reports}
