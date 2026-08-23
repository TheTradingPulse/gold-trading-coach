from __future__ import annotations
import math

def wilson_low(hits,n,z=1.96):
    if not n:return 0.0
    p=hits/n;d=1+z*z/n
    return (p+z*z/(2*n)-z*math.sqrt((p*(1-p)+z*z/(4*n))/n))/d

def bayes_rate(hits,n,prior=.35,strength=40):
    return (hits+prior*strength)/(n+strength) if n+strength else prior

def target_ev(p,r): return p*r-(1-p)

def decide(stats, stability_penalty=0.0, completeness=1.0):
    """Strict sniper gate. Uses conservative posterior + Wilson support.
    Does not force an ELITE classification."""
    n=int(stats.get("triggered",0) or 0)
    h3=int(stats.get("hit_3r",0) or 0);h5=int(stats.get("hit_5r",0) or 0)
    if n<30:return {"tier":"INSUFFICIENT_EVIDENCE","reason":"fewer than 30 triggered comparables"}
    p3=bayes_rate(h3,n,.35,40);p5=bayes_rate(h5,n,.22,40)
    w3=wilson_low(h3,n);w5=wilson_low(h5,n)
    ev3=target_ev(p3,3);ev5=target_ev(p5,5)
    best="5R" if ev5>ev3+.10 else "3R"
    best_ev=max(ev3,ev5)
    confidence=min(1.0,n/150.0)*max(.35,float(completeness))
    sniper=best_ev*confidence - float(stability_penalty)
    if n>=75 and w3>=.48 and best_ev>=1.0 and sniper>=.75:
        tier="ELITE"
    elif n>=45 and w3>=.38 and best_ev>=.55 and sniper>=.35:
        tier="WATCH"
    else:tier="RESEARCH"
    return {"tier":tier,"preferred_target":best,"posterior_3r":round(p3,4),
      "posterior_5r":round(p5,4),"wilson_3r_low":round(w3,4),"wilson_5r_low":round(w5,4),
      "ev_3r":round(ev3,4),"ev_5r":round(ev5,4),"sniper_edge":round(sniper,4),
      "triggered":n,"feature_completeness":round(float(completeness),3)}
