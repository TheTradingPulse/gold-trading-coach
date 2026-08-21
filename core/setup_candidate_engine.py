"""
The Trading Pulse - Setup Candidate Engine V2.9B

Separates raw ZONE QUALITY from actionable SETUP QUALITY.  The chart, filters,
and candidate panel use the setup grade.  A strong zone can therefore remain a
B/C setup when timing, room, conflict, or multi-timeframe context is weak.

Guardrails:
- Grades are deterministic quality scores, never win probabilities.
- Candidate grades never make Trade Ready true.
- Exact executable entry/stop/targets remain owned by trade_plan_engine after
  confirmation. Candidate planning levels are structural previews only.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
from typing import Any, Iterable, Optional

ENGINE_VERSION = "2.9B"
GRADE_RANK = {"D": 0, "C": 1, "B": 2, "A": 3, "A+": 4}
TIMEFRAME_WEIGHT = {"M": 10.0, "W": 10.0, "D": 10.0, "4H": 8.0, "1H": 6.0, "15m": 4.0, "5m": 2.0, "1m": 1.0}

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
        d=asdict(self); d["reasons"]=list(self.reasons); return d

def _f(v,d=0.0):
    try: return float(v) if v is not None else float(d)
    except (TypeError,ValueError): return float(d)

def _zone_key(z):
    return (str(getattr(z,"type","")).lower(),str(getattr(z,"timeframe","")),round(_f(getattr(z,"lower_bound",0)),4),round(_f(getattr(z,"upper_bound",0)),4))

def _overlap_ratio(a,b):
    alo,ahi=_f(a.lower_bound),_f(a.upper_bound); blo,bhi=_f(b.lower_bound),_f(b.upper_bound)
    overlap=max(0.0,min(ahi,bhi)-max(alo,blo)); smaller=max(min(ahi-alo,bhi-blo),.0001)
    return overlap/smaller

def _grade(score):
    if score>=92: return "A+"
    if score>=82: return "A"
    if score>=70: return "B"
    if score>=55: return "C"
    return "D"

def _lifecycle(price,lower,upper,distance_pct,width):
    if lower<=price<=upper: return "IN_ZONE"
    distance=min(abs(price-lower),abs(price-upper))
    if distance_pct<=.35 or distance<=max(width*1.5,.01): return "APPROACHING"
    return "FORMING"

def _same_zone(a,b): return a is not None and b is not None and _zone_key(a)==_zone_key(b)

def _nearest_opposing(ztype, entry, zones):
    if ztype=="demand":
        vals=[(_f(z.lower_bound),z) for z in zones if str(getattr(z,"type","")).lower()=="supply" and _f(z.lower_bound)>entry]
        return min(vals,key=lambda x:x[0]) if vals else (None,None)
    vals=[(_f(z.upper_bound),z) for z in zones if str(getattr(z,"type","")).lower()=="demand" and _f(z.upper_bound)<entry]
    return max(vals,key=lambda x:x[0]) if vals else (None,None)

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
        aligned=(ztype=="demand" and trend=="bullish") or (ztype=="supply" and trend=="bearish")
        nested=sum(1 for other in zones if other is not zone and str(getattr(other,"type","")).lower()==ztype and _overlap_ratio(zone,other)>=.50)
        # Raw zone quality: location-independent characteristics only.
        strength_pts=strength*.50; freshness_pts=freshness*.20
        retest_pts=15 if retests==0 else 10 if retests==1 else 5 if retests==2 else 0
        tf_pts=TIMEFRAME_WEIGHT.get(tf,2); nesting_pts=min(nested*5,5)
        zone_score=min(100,strength_pts+freshness_pts+retest_pts+tf_pts+nesting_pts); zone_grade=_grade(zone_score)
        width=upper-lower
        distance=lower-price if price<lower else price-upper if price>upper else 0
        distance_pct=distance/price*100 if price else 0; lifecycle=_lifecycle(price,lower,upper,distance_pct,width)
        # Structural preview. Entry is the proximal edge until price is actually in-zone;
        # executable entry remains current-price after confirmation in trade_plan_engine.
        projected_entry=(upper if ztype=="demand" and price<lower else lower if ztype=="supply" and price>upper else price if lower<=price<=upper else (lower if ztype=="demand" else upper))
        # Generic 2-tick preview buffer uses GC's current 0.10 tick only for GC; other symbols wait for their own engine.
        tick=.10 if symbol=="GC" else None
        projected_stop=(lower-2*tick if ztype=="demand" and tick else upper+2*tick if tick else None)
        target,opp=_nearest_opposing(ztype,projected_entry,zones)
        room=(abs(target-projected_entry) if target is not None else None)
        risk=(abs(projected_entry-projected_stop) if projected_stop is not None else None)
        rr=(room/risk if room is not None and risk and risk>0 else None)
        # Setup quality: zone quality plus timing/context, with real penalties.
        base=zone_score*.62
        alignment_pts=12 if aligned else 5 if trend=="neutral" else 0
        life_pts={"IN_ZONE":10,"APPROACHING":8,"FORMING":3,"QUALIFIED":10}.get(lifecycle,3)
        confluence_pts=min(nested*2.5,7.5)
        room_pts=10 if rr is not None and rr>=3 else 7 if rr is not None and rr>=2 else 3 if rr is not None and rr>=1 else 0
        width_pct=width/price*100 if price else 999; efficiency_pts=5 if width_pct<=.75 else 3 if width_pct<=1.5 else 0
        conflict_penalty=0
        if opp is not None and lower<=price<=upper and target is not None and room is not None and room<=width: conflict_penalty=12
        setup_score=max(0,min(100,base+alignment_pts+life_pts+confluence_pts+room_pts+efficiency_pts-conflict_penalty))
        grade=_grade(setup_score); selected_match=_same_zone(zone,selected); actionable=bool(selected_match and state_actionable)
        if actionable: lifecycle="QUALIFIED"
        reasons=(
            f"Zone quality {zone_grade} / {zone_score:.1f}: strength, freshness, retests, timeframe and nesting",
            f"Trend alignment contributes {alignment_pts:.1f}/12 ({trend})",
            f"Lifecycle {lifecycle} contributes {life_pts:.1f}/10",
            f"Multi-timeframe nesting contributes {confluence_pts:.1f}/7.5",
            f"Room to opposing structure contributes {room_pts:.1f}/10" + (f" ({rr:.2f}R preview)" if rr is not None else " (no preview target)"),
            f"Zone width efficiency contributes {efficiency_pts:.1f}/5",
            f"Conflict penalty {-conflict_penalty:.1f}" if conflict_penalty else "No immediate structural-conflict penalty",
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
    result.sort(key=lambda c:(c.distance_percent,-GRADE_RANK.get(c.grade,0)))
    return result[:limit] if limit is not None else result
