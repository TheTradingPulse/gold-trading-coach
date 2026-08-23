"""Trading Pulse V3.4 Pass 3C/3D - composite multi-market opportunity engine.

One deterministic policy classifies canonical setup candidates as WATCH or ELITE.
It preserves the setup engine score, adds no LLM judgement, and never journals.
1m/5m are confirmation timeframes: they may strengthen an overlapping higher-
timeframe idea, but cannot create a standalone Elite card.
"""
from __future__ import annotations
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from market_state_builder import build_market_state
from setup_candidate_engine import build_setup_candidates
from instruments import get_enabled_symbols

ENGINE_VERSION="3.4E"
from opportunity_policy import (
    ELITE_MIN_SCORE, WATCH_MIN_SCORE, ACTIVE_LIFECYCLES,
    STRUCTURAL_TIMEFRAMES, CONFIRMATION_TIMEFRAMES,
)
CONTEXT_TIMEFRAMES=("M","W","D","4H","1H")
TF_PRIORITY={"D":6,"4H":5,"1H":4,"15m":3,"5m":2,"1m":1}

@dataclass(frozen=True)
class EliteOpportunity:
    symbol:str; candidate:Any; market_state:Any; direction:str
    mtf_aligned:int; mtf_total:int; mtf_ratio:float
    composite_score:float; tier:str; confirmation_count:int=0
    @property
    def score(self): return float(self.candidate.setup_score)

def _direction(c): return "LONG" if str(c.zone_type).lower()=="demand" else "SHORT"
def _aligned(direction,trend):
    t=str(trend or '').lower(); return (direction=="LONG" and t=="bullish") or (direction=="SHORT" and t=="bearish")
def _mtf(c,state):
    d=_direction(c); trends=dict(getattr(state,'trends',{}) or {})
    usable=[str(trends.get(tf,'no_data') or 'no_data').lower() for tf in CONTEXT_TIMEFRAMES]
    usable=[t for t in usable if t in ('bullish','bearish','neutral')]
    if not usable:return 0,0,0.0
    a=sum(1 for t in usable if _aligned(d,t)); return a,len(usable),a/len(usable)
def _overlap(a,b):
    alo,ahi=float(a.lower_bound),float(a.upper_bound); blo,bhi=float(b.lower_bound),float(b.upper_bound)
    ov=max(0.0,min(ahi,bhi)-max(alo,blo)); smaller=max(min(ahi-alo,bhi-blo),1e-12); return ov/smaller

def _structural_ok(c,state):
    if str(c.lifecycle).upper() not in ACTIVE_LIFECYCLES:return False,'inactive_lifecycle'
    if float(c.zone_quality_score)<75:return False,'zone_quality_below_75'
    if float(c.freshness_score)<70:return False,'freshness_below_70'
    if int(c.retest_count)>1:return False,'too_many_retests'
    rr=c.projected_rr
    if rr is None:return False,'rr_unavailable'
    if float(rr)<2:return False,'rr_below_2'
    if float(rr)>50:return False,'rr_implausible_above_50'
    a,t,r=_mtf(c,state)
    if t>=3 and r<.40:return False,'mtf_below_40pct'
    return True,None

def _confirmation_count(c,all_candidates):
    if str(c.timeframe) not in STRUCTURAL_TIMEFRAMES:return 0
    return sum(1 for x in all_candidates if x is not c and str(x.timeframe) in CONFIRMATION_TIMEFRAMES
               and str(x.zone_type)==str(c.zone_type) and str(x.lifecycle).upper() in ACTIVE_LIFECYCLES
               and float(x.zone_quality_score)>=75 and _overlap(c,x)>=.35)

def _composite(c,state,confirmations):
    # Candidate score remains the dominant calibrated signal. Small deterministic
    # tie-breakers reward structural timeframe, MTF agreement and LTF confirmation.
    a,t,r=_mtf(c,state)
    tf_bonus={"D":1.5,"4H":1.25,"1H":1.0,"15m":.75}.get(str(c.timeframe),0.0)
    mtf_bonus=max(0.0,(r-.40)*2.0) if t else 0.0
    confirm_bonus=min(confirmations,2)*.35
    distance_penalty=min(max(float(c.distance_percent)-.35,0.0)*.5,1.0)
    return round(min(100.0,float(c.setup_score)+tf_bonus+mtf_bonus+confirm_bonus-distance_penalty),2)

def _collapse(opps):
    kept=[]
    for o in sorted(opps,key=lambda x:(0 if x.tier=='ELITE' else 1,-x.composite_score,float(x.candidate.distance_percent),-TF_PRIORITY.get(str(x.candidate.timeframe),0))):
        dup=next((p for p in kept if p.symbol==o.symbol and p.direction==o.direction and _overlap(p.candidate,o.candidate)>=.50),None)
        if dup is None: kept.append(o)
    return kept

def _scan_one(symbol):
    state=build_market_state(symbol); candidates=build_setup_candidates(state)
    stages={'raw':len(candidates),'score_8_5':0,'active_lifecycle':0,'structural_timeframe':0,'zone_quality_75':0,'freshness_70':0,'retests_le_1':0,'rr_valid':0,'mtf_40':0,'watch':0,'elite':0}
    rejected={}; opps=[]
    def rej(k): rejected.__setitem__(k,rejected.get(k,0)+1)
    for c in candidates:
        if float(c.setup_score)<WATCH_MIN_SCORE: rej('score_below_8_5'); continue
        stages['score_8_5']+=1
        if str(c.lifecycle).upper() not in ACTIVE_LIFECYCLES: rej('inactive_lifecycle'); continue
        stages['active_lifecycle']+=1
        if str(c.timeframe) not in STRUCTURAL_TIMEFRAMES:
            rej('confirmation_timeframe_only' if str(c.timeframe) in CONFIRMATION_TIMEFRAMES else 'timeframe_excluded'); continue
        stages['structural_timeframe']+=1
        if float(c.zone_quality_score)<75: rej('zone_quality_below_75'); continue
        stages['zone_quality_75']+=1
        if float(c.freshness_score)<70: rej('freshness_below_70'); continue
        stages['freshness_70']+=1
        if int(c.retest_count)>1: rej('too_many_retests'); continue
        stages['retests_le_1']+=1
        rr=c.projected_rr
        if rr is None: rej('rr_unavailable'); continue
        if float(rr)<2: rej('rr_below_2'); continue
        if float(rr)>50: rej('rr_implausible_above_50'); continue
        stages['rr_valid']+=1
        a,t,r=_mtf(c,state)
        if t>=3 and r<.40: rej('mtf_below_40pct'); continue
        stages['mtf_40']+=1
        conf=_confirmation_count(c,candidates); composite=_composite(c,state,conf)
        tier='ELITE' if float(c.setup_score)>=ELITE_MIN_SCORE else 'WATCH'
        stages[tier.lower()]+=1
        opps.append(EliteOpportunity(symbol,c,state,_direction(c),a,t,r,composite,tier,conf))
    return _collapse(opps),{'symbol':symbol,'stages':stages,'rejections':rejected,'error':None}

def scan_opportunity_snapshot(symbols=None,elite_limit=6,watch_limit=6):
    requested=[str(s).upper() for s in (symbols or get_enabled_symbols())]; allop=[]; reports={}; errors={}
    with ThreadPoolExecutor(max_workers=max(1,min(8,len(requested))),thread_name_prefix='tp-elite') as pool:
        fut={pool.submit(_scan_one,s):s for s in requested}
        for f in as_completed(fut):
            s=fut[f]
            try:o,r=f.result(); allop.extend(o); reports[s]=r
            except Exception as e: errors[s]=str(e); reports[s]={'symbol':s,'stages':{},'rejections':{},'error':str(e)}
    allop=_collapse(allop)
    allop.sort(key=lambda o:(0 if o.tier=='ELITE' else 1,-o.composite_score,float(o.candidate.distance_percent),-TF_PRIORITY.get(str(o.candidate.timeframe),0),o.symbol))
    elite=[o for o in allop if o.tier=='ELITE'][:max(0,int(elite_limit))]
    watch=[o for o in allop if o.tier=='WATCH'][:max(0,int(watch_limit))]
    keys=('raw','score_8_5','active_lifecycle','structural_timeframe','zone_quality_75','freshness_70','retests_le_1','rr_valid','mtf_40','watch','elite')
    glob={k:sum(int((reports.get(s,{}).get('stages') or {}).get(k,0)) for s in requested) for k in keys}
    rkeys=set(); [rkeys.update((r.get('rejections') or {}).keys()) for r in reports.values()]
    rejs={k:sum(int((reports.get(s,{}).get('rejections') or {}).get(k,0)) for s in requested) for k in sorted(rkeys)}
    return elite,watch,{'markets':{s:reports[s] for s in requested if s in reports},'global':glob,'rejections':rejs,'errors':errors,'displayed_elite':len(elite),'displayed_watch':len(watch)}

def scan_elite_snapshot(symbols=None,limit=6):
    elite,watch,diag=scan_opportunity_snapshot(symbols,elite_limit=limit,watch_limit=6)
    diag['watch_opportunities']=watch; diag['qualified_before_display_limit']=diag['global'].get('elite',0); diag['displayed']=len(elite)
    return elite,diag

def scan_elite_opportunities(symbols=None,limit=6): return scan_elite_snapshot(symbols,limit)[0]
