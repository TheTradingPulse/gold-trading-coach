"""Single production-facing grading authority for Trading Pulse.

Research engines may discover candidate rules, but only this service is allowed
to translate them into labels shown by the live dashboard.  It deliberately
fails closed: a historical evidence match remains unstarred until execution
ordering is verified by the canonical evidence adapter.
"""
from __future__ import annotations

from typing import Any

from elite_grading_adapter import grade_elite_candidate as _evidence_match
from data_truth_service import truth_status


POLICY_VERSION = "TP_LIVE_GRADING_SERVICE_1"
LIVE_STAR_TIER = "V4 ELITE"


def grade_live_candidate(candidate: Any, market_state: Any, symbol: str) -> dict[str, Any]:
    result = dict(_evidence_match(candidate, market_state, symbol))
    truth = truth_status()
    result["policy_version"] = POLICY_VERSION
    result["evidence_source"] = truth.evidence_source
    result["evidence_generated_utc"] = truth.evidence_generated_utc
    if not truth.live_promotion:
        result.update({
            "tier": "RESEARCH ONLY",
            "confidence10": None,
            "sample": 0,
            "execution_status": "NOT LIVE-PROMOTED",
            "live_eligible": False,
            "reason": truth.warning,
        })
        return result
    result.setdefault("execution_status", "UNVERIFIED")
    execution_verified = result.get("execution_status") == "VERIFIED"
    evidence_present = result.get("confidence10") is not None and int(result.get("sample") or 0) > 0
    result["live_eligible"] = bool(
        result.get("tier") == LIVE_STAR_TIER and execution_verified and evidence_present
    )
    if not result["live_eligible"] and result.get("tier") == LIVE_STAR_TIER:
        result["tier"] = "EVIDENCE MATCH"
        result["reason"] = (
            "Historical evidence matched, but canonical first-touch execution "
            "verification is incomplete."
        )
    return result


def has_live_star(decision: dict[str, Any]) -> bool:
    return bool(decision.get("live_eligible") and decision.get("tier") == LIVE_STAR_TIER)
