from __future__ import annotations
def professor_brief(candidate, calibrated, evidence=None):
    s=candidate if isinstance(candidate,dict) else candidate.__dict__
    symbol=s.get("symbol","?");side=s.get("direction","?");kind=s.get("setup_type","setup")
    tier=calibrated.get("tier","INSUFFICIENT_EVIDENCE")
    score=calibrated.get("calibrated_score10")
    parts=[f"{symbol} {kind} {side}",f"V4 tier: {tier}"]
    if score is not None:parts.append(f"calibrated score {float(score):.2f}/10")
    if evidence:
        n=evidence.get("triggered",0);p3=evidence.get("hit_3r_pct");p5=evidence.get("hit_5r_pct")
        parts.append(f"{n} triggered historical comparables")
        if p3 is not None:parts.append(f"3R hit {p3:.1f}%")
        if p5 is not None:parts.append(f"5R hit {p5:.1f}%")
    if tier=="INSUFFICIENT_EVIDENCE":
        parts.append("Confidence withheld because the comparable sample is too small.")
    elif tier=="ELITE":
        parts.append("Historically strong evidence; still requires current-chart confirmation.")
    elif tier=="WATCH":
        parts.append("Promising evidence, but not strong enough for Elite.")
    else:
        parts.append("Research-grade only; historical evidence does not justify promotion.")
    return "; ".join(parts)+"."
