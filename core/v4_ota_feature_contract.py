"""OTA-informed, inspectable structure components without invented inputs.

This is a feature contract, not a promoted scoring policy. Missing evidence
stays missing until the five-year calibration proves a safe treatment.
"""
from __future__ import annotations
from typing import Any, Mapping

MAX_POINTS={"strength":2.0,"base_time":1.0,"freshness":2.0,
            "trend":2.0,"curve":1.0,"profit_zone":2.0}


def _f(v):
    try:return float(v)
    except (TypeError,ValueError):return None


def components(candidate: Mapping[str,Any], context: Mapping[str,Any]) -> dict[str,Any]:
    reasons=candidate.get("reasons") or []
    strength=_f(candidate.get("strength",candidate.get("zone_strength")))
    freshness=_f(candidate.get("freshness_score",candidate.get("freshness")))
    retests=_f(candidate.get("retest_count",candidate.get("retests")))
    rr=_f(candidate.get("projected_rr",context.get("projected_rr")))
    aligned=_f(context.get("htf_aligned_count"));known=_f(context.get("htf_known_count"))
    out={
      "strength":{"raw":strength,"available":strength is not None},
      "base_time":{"raw":candidate.get("basing_candles"),"available":candidate.get("basing_candles") is not None},
      "freshness":{"raw":freshness,"retests":retests,"penetration_pct":candidate.get("penetration_pct"),
                   "available":freshness is not None},
      "trend":{"aligned":aligned,"known":known,"available":aligned is not None and known not in (None,0)},
      "curve":{"location":context.get("curve_location"),"available":context.get("curve_location") is not None},
      "profit_zone":{"projected_rr":rr,"available":rr is not None},
    }
    available=sum(bool(v["available"]) for v in out.values())
    return {"schema":"tp.ota-reference.v1","components":out,"available_components":available,
            "complete":available==len(MAX_POINTS),"note":"Reference features only; weights require chronological OOS validation."}
