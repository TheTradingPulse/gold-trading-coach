from __future__ import annotations
from v4_calibrated_policy import V4CalibratedPolicy
from v4_professor_chart_context import calibrated_chart_context

def enrich_candidate(candidate, calibration_path="research_data/v4/v4_calibration.json"):
    """Non-mutating V4 research enrichment for a canonical candidate."""
    policy=V4CalibratedPolicy(calibration_path)
    scoring=policy.classify(candidate)
    professor=calibrated_chart_context(candidate,calibration_path)
    if isinstance(candidate,dict):
        base=dict(candidate)
    else:
        base={k:getattr(candidate,k) for k in dir(candidate) if not k.startswith("_") and not callable(getattr(candidate,k,None))}
    return {
        "candidate":base,
        "v4_scoring":scoring,
        "professor_chart_context":professor,
        "research_only":True,
        "live_v3_4_untouched":True,
    }
