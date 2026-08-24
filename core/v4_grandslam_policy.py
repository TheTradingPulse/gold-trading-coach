from __future__ import annotations
import math
from v4_sniper_policy import wilson_low, bayes_rate, target_ev

POLICY_VERSION = "V4_GRANDSLAM_1"

def _clip(v, lo=0.0, hi=1.0): return max(lo, min(hi, float(v)))

def decide_grandslam(stats, *, completeness=1.0, mean_similarity=1.0, stability_penalty=0.0,
                     projected_rr=None, actionable=None):
    """Strict research tiering. GRAND_SLAM is deliberately rare and cannot be created by raw score."""
    n=int(stats.get("triggered",0) or 0); h3=int(stats.get("hit_3r",0) or 0); h5=int(stats.get("hit_5r",0) or 0)
    base={"policy_version":POLICY_VERSION,"triggered":n,"feature_completeness":round(float(completeness or 0),3),
          "mean_similarity":round(float(mean_similarity or 0),3)}
    if n < 40:
        return {**base,"tier":"INSUFFICIENT_EVIDENCE","reason":"fewer than 40 triggered contextual comparables"}
    p3=bayes_rate(h3,n,.35,60); p5=bayes_rate(h5,n,.22,60)
    w3=wilson_low(h3,n); w5=wilson_low(h5,n)
    ev3=target_ev(p3,3); ev5=target_ev(p5,5)
    comp=_clip(completeness); sim=_clip(mean_similarity)
    sample=min(1.0, math.sqrt(n/180.0))
    confidence=sample*(.45+.55*comp)*(.55+.45*sim)
    edge=max(ev3,ev5)*confidence-float(stability_penalty or 0)
    rr_ok = projected_rr is None or float(projected_rr) >= 3.0
    action_ok = actionable is None or bool(actionable)
    # Grand Slam requires strong evidence for BOTH objectives, large sample, rich context,
    # close analogues and structural room. No raw-score threshold is used.
    if (n>=100 and w3>=.70 and w5>=.55 and ev3>=1.65 and ev5>=2.35 and
        comp>=.70 and sim>=.76 and rr_ok and action_ok and edge>=1.55):
        tier="GRAND_SLAM"
    elif (n>=80 and w3>=.55 and w5>=.35 and ev3>=1.15 and
          comp>=.62 and sim>=.72 and rr_ok and action_ok and edge>=.90):
        tier="ELITE"
    elif n>=55 and w3>=.42 and ev3>=.55 and comp>=.52 and sim>=.69 and edge>=.35:
        tier="WATCH"
    else:
        tier="RESEARCH"
    preferred="5R" if ev5>=ev3+.18 and w5>=.35 else "3R"
    return {**base,"tier":tier,"preferred_target":preferred,"posterior_3r":round(p3,4),"posterior_5r":round(p5,4),
            "wilson_3r_low":round(w3,4),"wilson_5r_low":round(w5,4),"ev_3r":round(ev3,4),"ev_5r":round(ev5,4),
            "evidence_edge":round(edge,4),"structural_3r_room":bool(rr_ok),"actionable_gate":bool(action_ok),
            "reason":"evidence-backed contextual tier; raw score cannot promote tier"}
