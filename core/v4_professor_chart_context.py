from __future__ import annotations
from v4_calibrated_policy import V4CalibratedPolicy

def calibrated_chart_context(candidate, calibration_path="research_data/v4/v4_calibration.json"):
    r=V4CalibratedPolicy(calibration_path).classify(candidate)
    g=r.get("evidence_group") or {}
    return {
        "calibrated_score10":r["calibrated_score10"],
        "research_tier":r["tier"],
        "raw_score10":r["raw_score10"],
        "evidence_score10":r["evidence_score10"],
        "comparable_triggered":r["triggered_sample"],
        "historical_3r_hit_pct":g.get("hit_3r_pct"),
        "historical_5r_hit_pct":g.get("hit_5r_pct"),
        "historical_avg_mfe_r":g.get("avg_mfe_r"),
        "historical_avg_mae_r":g.get("avg_mae_r"),
        "evidence_explanation":r["explanation"],
        "research_only":True,
    }
