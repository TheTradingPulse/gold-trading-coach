"""The Trading Pulse - Historical Evidence + Explainable Scoring V2.8E."""
from dataclasses import dataclass, asdict
from math import sqrt
from typing import Iterable, Optional

MIN_SAMPLE=30
STRONG_SAMPLE=100

@dataclass
class EvidenceSummary:
    sample_size:int=0; wins:int=0; losses:int=0; unresolved:int=0; ambiguous:int=0
    observed_win_rate:Optional[float]=None; average_realized_r:Optional[float]=None
    profit_factor:Optional[float]=None; confidence:str="INSUFFICIENT_SAMPLE"
    wilson_low:Optional[float]=None; wilson_high:Optional[float]=None
    note:str="Historical evidence, not a predicted probability."
    def to_dict(self): return asdict(self)

def _wilson(w,n,z=1.96):
    if n<=0:return (None,None)
    p=w/n; den=1+z*z/n; center=(p+z*z/(2*n))/den
    margin=z*sqrt((p*(1-p)+z*z/(4*n))/n)/den
    return round(max(0,center-margin)*100,2),round(min(1,center+margin)*100,2)

def summarize_outcomes(outcomes:Iterable) -> EvidenceSummary:
    rows=[o.to_dict() if hasattr(o,"to_dict") else dict(o) for o in outcomes]
    wins=sum(r.get("status")=="WIN" for r in rows); losses=sum(r.get("status")=="LOSS" for r in rows)
    unresolved=sum(r.get("status")=="UNRESOLVED" for r in rows); ambiguous=sum(r.get("status")=="AMBIGUOUS" for r in rows)
    resolved=wins+losses; vals=[float(r["realized_r"]) for r in rows if r.get("realized_r") is not None and r.get("status") in {"WIN","LOSS"}]
    gross_win=sum(v for v in vals if v>0); gross_loss=abs(sum(v for v in vals if v<0))
    conf="HIGH" if resolved>=STRONG_SAMPLE else "MODERATE" if resolved>=MIN_SAMPLE else "INSUFFICIENT_SAMPLE"
    lo,hi=_wilson(wins,resolved)
    return EvidenceSummary(len(rows),wins,losses,unresolved,ambiguous,round(wins/resolved*100,2) if resolved else None,round(sum(vals)/len(vals),4) if vals else None,round(gross_win/gross_loss,3) if gross_loss else None,conf,lo,hi)

def explainable_setup_score(fingerprint:dict, evidence:Optional[EvidenceSummary]=None)->dict:
    m=fingerprint.get("market",{}); s=fingerprint.get("structure",{}); c=fingerprint.get("confirmation",{}); t=fingerprint.get("trade",{})
    alignment=float(m.get("alignment_score") or 0); zone=(s.get("execution_zone") or {}); strength=float(zone.get("strength") or 0); rr=float(t.get("rr_ratio") or 0)
    confirmation=sum(bool(c.get(k)) for k in ("price_in_zone","lower_timeframe_confirmed","structural_trigger","risk_validated"))/4
    current=min(100, alignment*.35 + strength*.25 + min(rr/3,1)*20 + confirmation*20)
    hist=None
    if evidence and evidence.confidence!="INSUFFICIENT_SAMPLE" and evidence.observed_win_rate is not None:
        # Evidence contribution is intentionally bounded; it cannot override bad current structure.
        hist=max(0,min(100,evidence.observed_win_rate))
        total=.75*current+.25*hist
    else: total=current
    grade="A+" if total>=90 else "A" if total>=80 else "B" if total>=70 else "C" if total>=60 else "D"
    return {"score":round(total,1),"grade":grade,"current_quality":round(current,1),"historical_component":round(hist,1) if hist is not None else None,"historical_confidence":evidence.confidence if evidence else "NONE","explanation":{"alignment":alignment,"zone_strength":strength,"available_rr":rr,"confirmation_fraction":confirmation,"sample_size":evidence.sample_size if evidence else 0},"warning":"Historical observations are evidence, not a forecast or guaranteed probability."}
