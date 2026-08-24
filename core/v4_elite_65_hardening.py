from __future__ import annotations
import json, math, sqlite3, statistics
from pathlib import Path
from collections import defaultdict

VERSION="V4_ELITE_65_HARDENING_1"
TARGET_WIN=0.65

def j(x):
    try:return json.loads(x or "{}")
    except:return {}

def wilson(k,n,z=1.96):
    if not n:return 0.0
    p=k/n; d=1+z*z/n
    return (p+z*z/(2*n)-z*math.sqrt((p*(1-p)+z*z/(4*n))/n))/d

def stats(rows,target=3,slip_r=0.0):
    t=[r for r in rows if int(r.get("entered") or 0)]
    n=len(t); key="primary_hit" if target==3 else "stretch_hit"
    h=sum(int(r.get(key) or 0) for r in t); p=h/n if n else 0
    # conservative fixed-target expectancy, then stress every trade by slippage/fees in R
    ev=(p*target-(1-p)-slip_r) if n else None
    losses=n-h
    return {"assigned":len(rows),"triggered":n,"hits":h,"losses":losses,
            "hit_pct":round(100*p,2) if n else None,"wilson_low_pct":round(100*wilson(h,n),2) if n else None,
            "ev_r":round(ev,4) if ev is not None else None}

def load(db):
    con=sqlite3.connect(str(db));con.row_factory=sqlite3.Row
    rows=[dict(x) for x in con.execute("select * from observations order by as_of,id")]
    con.close();return rows

def ctx(r):
    c=j(r.get("context_json")); q=j(r.get("candidate_json"))
    return {
      "symbol":r.get("symbol"),"setup_type":str(r.get("setup_type","")).lower(),"direction":str(r.get("direction","")).upper(),
      "session":c.get("session_utc") or c.get("session") or "UNKNOWN",
      "trend_1h":c.get("trend_1h") or "UNKNOWN","trend_4h":c.get("trend_4h") or "UNKNOWN",
      "volatility":c.get("volatility_15m") or c.get("volatility_regime") or "UNKNOWN",
      "grade":c.get("grade") or r.get("grade") or "UNKNOWN",
      "lifecycle":c.get("lifecycle") or r.get("lifecycle") or "UNKNOWN",
      "projected_rr":c.get("projected_rr",q.get("projected_rr")),
      "htf":c.get("htf_aligned_count"),
      "zone_quality":c.get("zone_quality"),
    }

def rrbin(v):
    try:v=float(v)
    except:return "?"
    if v<2:return "<2"
    if v<3:return "2-3"
    if v<4:return "3-4"
    if v<5:return "4-5"
    return "5+"

def val(r,f):
    c=ctx(r)
    if f=="rr":return rrbin(c["projected_rr"])
    return str(c.get(f,"UNKNOWN"))

FEATURE_SETS=[
 ("symbol","setup_type","direction","rr"),
 ("symbol","setup_type","direction","session","rr"),
 ("symbol","setup_type","direction","trend_1h","rr"),
 ("symbol","setup_type","direction","trend_4h","rr"),
 ("symbol","setup_type","direction","volatility","rr"),
 ("symbol","setup_type","direction","grade","rr"),
 ("symbol","setup_type","direction","lifecycle","rr"),
 ("symbol","setup_type","direction","session","trend_1h","rr"),
]

def key(r,fs):return tuple(val(r,f) for f in fs)

def monthly_stability(rows):
    g=defaultdict(list)
    for r in rows:g[str(r.get("as_of"))[:7]].append(r)
    usable=[stats(v,3) for v in g.values() if stats(v,3)["triggered"]>=8]
    if not usable:return {"months":0,"positive":0,"median_hit":0,"worst_hit":0}
    hits=[x["hit_pct"]/100 for x in usable]
    return {"months":len(hits),"positive":sum(x["ev_r"]>0 for x in usable)/len(usable),
            "median_hit":statistics.median(hits),"worst_hit":min(hits)}

def discover(rows,mintrig=60):
    out=[]
    for fs in FEATURE_SETS:
        g=defaultdict(list)
        for r in rows:g[key(r,fs)].append(r)
        for k,rs in g.items():
            s3=stats(rs,3);s5=stats(rs,5)
            if s3["triggered"]<mintrig:continue
            st=monthly_stability(rs)
            # 65% is a desired precision target, not forced by relabeling.
            score=(s3["wilson_low_pct"] or 0)+.35*(s5["wilson_low_pct"] or 0)+5*st["positive"]
            out.append({"features":fs,"values":k,"s3":s3,"s5":s5,"stability":st,"score":score})
    return sorted(out,key=lambda x:x["score"],reverse=True)

def match(r,q):return key(r,q["features"])==tuple(q["values"])
def selected(rows,rules):return [r for r in rows if any(match(r,q) for q in rules)]

def streak(rows,target=3):
    keyhit="primary_hit" if target==3 else "stretch_hit";cur=mx=0
    for r in rows:
        if not int(r.get("entered") or 0):continue
        if int(r.get(keyhit) or 0):cur=0
        else:cur+=1;mx=max(mx,cur)
    return mx

def breakdown(rows,field,target=3):
    g=defaultdict(list)
    for r in rows:g[val(r,field)].append(r)
    return {k:stats(v,target) for k,v in g.items() if stats(v,target)["triggered"]>=20}

def run(db,outdir):
    rows=load(db);n=len(rows);a=int(n*.50);b=int(n*.70);c=int(n*.85)
    disc,cal,valset,hold=rows[:a],rows[a:b],rows[b:c],rows[c:]
    pool=discover(disc)
    survivors=[]
    for q in pool:
        cr=selected(cal,[q]); cs=stats(cr,3)
        # High-precision candidate gate. We do NOT lower this just to create trades.
        if cs["triggered"]>=30 and cs["hit_pct"]>=62 and cs["wilson_low_pct"]>=52 and q["stability"]["months"]>=3 and q["stability"]["positive"]>=.70:
            qq=dict(q);qq["calibration3"]=cs;survivors.append(qq)
    # Freeze increasingly selective rule sets before validation.
    tiers={}
    for name,count in [("TOP40",40),("TOP20",20),("TOP10",10),("TOP5",5)]:
        rules=survivors[:count]; vr=selected(valset,rules)
        tiers[name]={"rules":rules,"validation3":stats(vr,3),"validation5":stats(vr,5)}
    # Choose precision frontier on validation, but require sample; then freeze for final holdout.
    eligible=[(name,x) for name,x in tiers.items() if x["validation3"]["triggered"]>=100]
    chosen=max(eligible,key=lambda z:(z[1]["validation3"]["hit_pct"],z[1]["validation3"]["wilson_low_pct"])) if eligible else ("NONE",{"rules":[]})
    frozen=chosen[1]["rules"]; hr=selected(hold,frozen)
    h3=stats(hr,3);h5=stats(hr,5)
    # Adversarial tests on final untouched holdout.
    market=breakdown(hr,"symbol",3); direction=breakdown(hr,"direction",3); session=breakdown(hr,"session",3)
    leave_one={}
    for sym in sorted({r.get("symbol") for r in hr}):
        x=[r for r in hr if r.get("symbol")!=sym];leave_one[str(sym)]=stats(x,3)
    stress={str(s):stats(hr,3,s) for s in (0.0,.05,.10,.20,.30)}
    rolling=breakdown(hr,"month",3) if False else {}
    mg=defaultdict(list)
    for r in hr:mg[str(r.get("as_of"))[:7]].append(r)
    rolling={k:stats(v,3) for k,v in mg.items() if stats(v,3)["triggered"]>=20}
    all_slices=list(market.values())+list(direction.values())
    slice_floor=min((x["hit_pct"] for x in all_slices if x["hit_pct"] is not None),default=0)
    # 65% target is aspirational. Promotion requires actual holdout >=65 and conservative lower bound >=60.
    precision65=bool(h3["triggered"]>=200 and h3["hit_pct"]>=65 and h3["wilson_low_pct"]>=60)
    robust=bool(precision65 and slice_floor>=55 and stats(hr,3,.20)["ev_r"]>=1.0)
    report={"version":VERSION,"target_precision_pct":65,"rows":n,
      "splits":{"discovery":len(disc),"calibration":len(cal),"validation":len(valset),"final_holdout":len(hold)},
      "survivor_rules":len(survivors),"precision_frontier":{k:{"validation3":v["validation3"],"validation5":v["validation5"],"rules":len(v["rules"])} for k,v in tiers.items()},
      "chosen_frozen_set":chosen[0],"final_holdout":{"3R":h3,"5R":h5,"max_losing_streak_3R":streak(hr,3)},
      "adversarial":{"market":market,"direction":direction,"session":session,"leave_one_market_out":leave_one,"slippage_stress_r":stress,"rolling_months":rolling},
      "gates":{"actual_65pct":precision65,"robust":robust,"slice_floor_pct":slice_floor},
      "status":"65PCT_SNIPER_CANDIDATE" if robust else "KEEP_RESEARCH_ONLY",
      "frozen_rules":frozen}
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
    (out/"elite_65_hardening_report.json").write_text(json.dumps(report,indent=2,default=str),encoding="utf-8")
    (out/"frozen_65_rules.json").write_text(json.dumps(frozen,indent=2,default=str),encoding="utf-8")
    return report
