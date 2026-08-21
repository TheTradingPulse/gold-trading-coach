"""
The Trading Pulse - Setup Candidate Engine V2.12 FINAL

Calibrated deterministic grading for the final single-symbol V2 build.

Principles:
- Raw ZONE QUALITY and actionable SETUP QUALITY are separate.
- 9+/10 is rare and requires elite quality without a fatal structural flaw.
- Strong characteristics cannot simply add their way around a major weakness.
- Quality gates/caps are applied after bonuses and penalties.
- Grades are educational quality scores, never win probabilities.
- Candidate grades never make Trade Ready true.
- Exact executable entry/stop/targets remain owned by trade_plan_engine after
  confirmation. Candidate planning levels are structural previews only.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
from typing import Any, Iterable, Optional
from instruments import get_instrument
from risk_model import structural_stop

ENGINE_VERSION = "3.1E"
GRADE_RANK = {"D": 0, "C": 1, "B": 2, "A": 3, "A+": 4}
TIMEFRAME_WEIGHT = {"M": 10.0, "W": 10.0, "D": 10.0, "4H": 8.0, "1H": 6.0, "15m": 4.0, "5m": 2.0, "1m": 1.0}
CONTEXT_TIMEFRAMES = ("M", "W", "D", "4H", "1H")

@dataclass(frozen=True)
class SetupCandidate:
    candidate_id: str; symbol: str; zone_type: str; timeframe: str
    lower_bound: float; upper_bound: float; midpoint: float; width_points: float
    current_price: float; distance_points: float; distance_percent: float
    strength: float; freshness_score: float; retest_count: int; trend: str
    trend_aligned: bool; nested_confluence: int
    zone_quality_score: float; zone_grade: str
    setup_score: float; quality_score: float; grade: str
    lifecycle: str; is_selected_zone: bool; is_actionable: bool
    opposing_room_points: Optional[float]; projected_entry: Optional[float]
    projected_stop: Optional[float]; projected_target: Optional[float]
    projected_rr: Optional[float]; reasons: tuple[str, ...]
    def to_dict(self):
        d = asdict(self); d["reasons"] = list(self.reasons); return d

def _f(v, d=0.0):
    try: return float(v) if v is not None else float(d)
    except (TypeError, ValueError): return float(d)

def _zone_key(z):
    return (str(getattr(z,"type","")).lower(), str(getattr(z,"timeframe","")), round(_f(getattr(z,"lower_bound",0)),4), round(_f(getattr(z,"upper_bound",0)),4))

def _overlap_ratio(a,b):
    alo,ahi=_f(a.lower_bound),_f(a.upper_bound); blo,bhi=_f(b.lower_bound),_f(b.upper_bound)
    overlap=max(0.0,min(ahi,bhi)-max(alo,blo)); smaller=max(min(ahi-alo,bhi-blo),.0001)
    return overlap/smaller

def _grade(score):
    # Deliberately demanding. A+ should be exceptional, not routine.
    if score >= 94: return "A+"
    if score >= 86: return "A"
    if score >= 74: return "B"
    if score >= 60: return "C"
    return "D"

def _lifecycle(price,lower,upper,distance_pct,width):
    if lower <= price <= upper: return "IN_ZONE"
    distance=min(abs(price-lower),abs(price-upper))
    if distance_pct <= .35 or distance <= max(width*1.5,.01): return "APPROACHING"
    return "FORMING"

def _same_zone(a,b): return a is not None and b is not None and _zone_key(a)==_zone_key(b)

def _nearest_opposing(ztype, entry, zones):
    if ztype=="demand":
        vals=[(_f(z.lower_bound),z) for z in zones if str(getattr(z,"type","")).lower()=="supply" and _f(z.lower_bound)>entry]
        return min(vals,key=lambda x:x[0]) if vals else (None,None)
    vals=[(_f(z.upper_bound),z) for z in zones if str(getattr(z,"type","")).lower()=="demand" and _f(z.upper_bound)<entry]
    return max(vals,key=lambda x:x[0]) if vals else (None,None)

def _directional_alignment(ztype, trend):
    return (ztype=="demand" and trend=="bullish") or (ztype=="supply" and trend=="bearish")

def _mtf_context(ztype, trends):
    usable=[str(trends.get(tf,"no_data") or "no_data").lower() for tf in CONTEXT_TIMEFRAMES]
    usable=[t for t in usable if t in ("bullish","bearish","neutral")]
    if not usable: return 0,0,0.0
    aligned=sum(_directional_alignment(ztype,t) for t in usable)
    return aligned,len(usable),aligned/len(usable)

def build_setup_candidates(state: Any) -> list[SetupCandidate]:
    price=_f(getattr(state,"current_price",None),0)
    if price<=0: return []
    symbol=str(getattr(state,"root_symbol","GC") or "GC").upper(); trends=dict(getattr(state,"trends",{}) or {})
    selected=getattr(state,"selected_zone",None); state_actionable=bool(getattr(state,"is_actionable",False))
    zones=list(getattr(state,"supply_zones",[]) or [])+list(getattr(state,"demand_zones",[]) or [])
    out=[]
    for zone in zones:
        ztype=str(getattr(zone,"type","")).lower(); tf=str(getattr(zone,"timeframe","") or "")
        lower=_f(getattr(zone,"lower_bound",None)); upper=_f(getattr(zone,"upper_bound",None))
        if ztype not in ("supply","demand") or lower<=0 or upper<=lower: continue
        strength=min(max(_f(getattr(zone,"strength",0)),0),100); freshness=min(max(_f(getattr(zone,"freshness_score",0)),0),100)
        retests=max(int(_f(getattr(zone,"retest_count",0),0)),0); trend=str(trends.get(tf,"neutral") or "neutral").lower()
        aligned=_directional_alignment(ztype,trend)
        nested=sum(1 for other in zones if other is not zone and str(getattr(other,"type","")).lower()==ztype and _overlap_ratio(zone,other)>=.50)

        # Raw zone quality: location-independent characteristics only.
        strength_pts=strength*.48; freshness_pts=freshness*.22
        retest_pts=16 if retests==0 else 10 if retests==1 else 4 if retests==2 else 0
        tf_pts=TIMEFRAME_WEIGHT.get(tf,2); nesting_pts=min(nested*4,4)
        zone_score=min(100,strength_pts+freshness_pts+retest_pts+tf_pts+nesting_pts); zone_grade=_grade(zone_score)

        width=upper-lower
        distance=lower-price if price<lower else price-upper if price>upper else 0
        distance_pct=distance/price*100 if price else 0; lifecycle=_lifecycle(price,lower,upper,distance_pct,width)
        projected_entry=(upper if ztype=="demand" and price<lower else lower if ztype=="supply" and price>upper else price if lower<=price<=upper else (lower if ztype=="demand" else upper))
        instrument=get_instrument(symbol); tick=instrument.tick_size
        direction="LONG" if ztype=="demand" else "SHORT"
        risk_preview=structural_stop(instrument,direction,projected_entry,lower,upper,tf)
        projected_stop=risk_preview.stop
        target,opp=_nearest_opposing(ztype,projected_entry,zones)
        room=(abs(target-projected_entry) if target is not None else None)
        risk=(abs(projected_entry-projected_stop) if projected_stop is not None else None)
        rr=(room/risk if room is not None and risk and risk>0 else None)
        width_pct=width/price*100 if price else 999
        mtf_aligned,mtf_total,mtf_ratio=_mtf_context(ztype,trends)

        # V2.12 calibrated setup quality.
        # Start with quality; add independent evidence; subtract weaknesses; then
        # enforce caps so a fatal flaw cannot be hidden by unrelated bonuses.
        base=zone_score*.55
        alignment_pts=10 if aligned else 3 if trend=="neutral" else 0
        mtf_pts=10 if mtf_ratio>=.80 else 7 if mtf_ratio>=.60 else 4 if mtf_ratio>=.40 else 0
        life_pts={"IN_ZONE":9,"APPROACHING":7,"FORMING":2,"QUALIFIED":9}.get(lifecycle,2)
        confluence_pts=min(nested*2.0,6.0)
        room_pts=7 if rr is not None and rr>=3 else 5 if rr is not None and rr>=2 else 3 if rr is not None and rr>=1.5 else 0
        efficiency_pts=3 if width_pct<=.75 else 1 if width_pct<=1.5 else 0

        penalties=0.0
        penalty_reasons=[]
        if trend not in ("neutral","no_data") and not aligned:
            penalties+=10; penalty_reasons.append("local trend conflicts with setup direction")
        if retests>=3:
            penalties+=12; penalty_reasons.append("zone has 3+ retests")
        elif retests==2:
            penalties+=5; penalty_reasons.append("zone has 2 retests")
        if freshness<50:
            penalties+=10; penalty_reasons.append("freshness below 50")
        elif freshness<70:
            penalties+=4; penalty_reasons.append("freshness below 70")
        if rr is not None and rr<1:
            penalties+=18; penalty_reasons.append("preview reward/risk below 1R")
        elif rr is not None and rr<1.5:
            penalties+=10; penalty_reasons.append("preview reward/risk below 1.5R")
        elif rr is not None and rr<2:
            penalties+=4; penalty_reasons.append("preview reward/risk below 2R")
        if width_pct>1.5:
            penalties+=5; penalty_reasons.append("zone is structurally wide")
        if mtf_total>=3 and mtf_ratio<.40:
            penalties+=8; penalty_reasons.append("higher-timeframe context is poorly aligned")
        conflict=bool(opp is not None and target is not None and room is not None and room<=max(width*1.25,.01))
        if conflict:
            penalties+=15; penalty_reasons.append("opposing structure is too close")

        raw_score=base+alignment_pts+mtf_pts+life_pts+confluence_pts+room_pts+efficiency_pts-penalties
        score_cap=100.0
        cap_reasons=[]
        if lifecycle=="FORMING": score_cap=min(score_cap,89.0); cap_reasons.append("forming setup capped below 9.0")
        if not aligned and trend not in ("neutral","no_data"): score_cap=min(score_cap,85.0); cap_reasons.append("counter-trend setup cannot grade A+")
        if retests>=2: score_cap=min(score_cap,87.0); cap_reasons.append("2+ retests cap elite grade")
        if retests>=3: score_cap=min(score_cap,79.0); cap_reasons.append("3+ retests cap setup at B-range")
        if freshness<70: score_cap=min(score_cap,86.0); cap_reasons.append("sub-70 freshness caps elite grade")
        if freshness<50: score_cap=min(score_cap,78.0); cap_reasons.append("low freshness caps setup at B-range")
        if rr is not None and rr<2: score_cap=min(score_cap,85.0); cap_reasons.append("sub-2R preview cannot grade A+")
        if rr is not None and rr<1.5: score_cap=min(score_cap,76.0); cap_reasons.append("sub-1.5R preview caps setup at B-range")
        if rr is not None and rr<1: score_cap=min(score_cap,59.0); cap_reasons.append("sub-1R preview caps setup below C")
        if conflict: score_cap=min(score_cap,74.0); cap_reasons.append("immediate opposing structure caps setup at B threshold")
        if mtf_total>=3 and mtf_ratio<.40: score_cap=min(score_cap,82.0); cap_reasons.append("weak MTF context caps setup below A")
        if zone_score<75: score_cap=min(score_cap,89.0); cap_reasons.append("zone quality below 7.5 caps setup below 9.0")

        setup_score=max(0,min(100,raw_score,score_cap))
        grade=_grade(setup_score); selected_match=_same_zone(zone,selected); actionable=bool(selected_match and state_actionable)
        if actionable: lifecycle="QUALIFIED"
        reasons=(
            f"Zone quality {zone_grade} / {zone_score:.1f}: strength, freshness, retests, timeframe and nesting",
            f"Local trend alignment contributes {alignment_pts:.1f}/10 ({trend})",
            f"Higher-timeframe context contributes {mtf_pts:.1f}/10 ({mtf_aligned}/{mtf_total} aligned)",
            f"Lifecycle {lifecycle} contributes {life_pts:.1f}/9",
            f"Multi-timeframe nesting contributes {confluence_pts:.1f}/6",
            f"Room to opposing structure contributes {room_pts:.1f}/7" + (f" ({rr:.2f}R preview using adaptive structural stop)" if rr is not None else " (no preview target)"),
            f"Risk model: {risk_preview.buffer_ticks:.0f}-tick / {risk_preview.buffer_points:.4f}-point buffer beyond zone edge; total preview risk {risk_preview.risk_points:.4f} pts",
            f"Zone width efficiency contributes {efficiency_pts:.1f}/3",
            f"Quality penalties -{penalties:.1f}: " + ("; ".join(penalty_reasons) if penalty_reasons else "none"),
            f"Quality ceiling {score_cap:.1f}: " + ("; ".join(cap_reasons) if cap_reasons else "no limiting flaw"),
            "9+/10 requires elite quality with no major structural weakness",
        )
        raw=f"{symbol}|{ztype}|{tf}|{lower:.4f}|{upper:.4f}"; cid=sha256(raw.encode()).hexdigest()[:16]
        out.append(SetupCandidate(cid,symbol,ztype,tf,round(lower,4),round(upper,4),round((lower+upper)/2,4),round(width,4),round(price,4),round(distance,4),round(distance_pct,4),round(strength,2),round(freshness,2),retests,trend,aligned,nested,round(zone_score,1),zone_grade,round(setup_score,1),round(setup_score,1),grade,lifecycle,selected_match,actionable,round(room,4) if room is not None else None,round(projected_entry,4),round(projected_stop,4) if projected_stop is not None else None,round(target,4) if target is not None else None,round(rr,2) if rr is not None else None,reasons))
    out.sort(key=lambda c:(-GRADE_RANK.get(c.grade,0),c.distance_percent,-TIMEFRAME_WEIGHT.get(c.timeframe,0)))
    return out

def filter_candidates(candidates: Iterable[SetupCandidate], minimum_grade="B", enabled_grades: Optional[dict[str,bool]]=None, relevant_timeframes: Optional[set[str]]=None, limit: Optional[int]=None):
    minimum_grade=str(minimum_grade or "ALL").upper(); threshold=-1 if minimum_grade=="ALL" else GRADE_RANK.get(minimum_grade,0)
    enabled=enabled_grades or {"A+":True,"A":True,"B":True,"C":True,"D":True}; result=[]
    for c in candidates:
        if GRADE_RANK.get(c.grade,0)<threshold or not enabled.get(c.grade,False): continue
        if relevant_timeframes is not None and c.timeframe not in relevant_timeframes: continue
        result.append(c)
    result.sort(key=lambda c:(c.distance_percent,-GRADE_RANK.get(c.grade,0),-c.setup_score))
    return result[:limit] if limit is not None else result



