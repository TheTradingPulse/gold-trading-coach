from __future__ import annotations
from collections import defaultdict
from statistics import mean, pstdev
from v4_oos_validation import load_ordered
from v4_calibration_engine import _stats, score_bucket

TIERS=("ELITE","WATCH","RESEARCH","INSUFFICIENT_EVIDENCE")

def _key(r):
    return (r["symbol"],r["setup_type"],r["direction"],score_bucket(r["score10"]))

def _parent_keys(r):
    return [
      ("exact", r["symbol"],r["setup_type"],r["direction"],score_bucket(r["score10"])),
      ("family",r["symbol"],r["setup_type"],r["direction"]),
      ("market",r["symbol"],r["direction"]),
      ("global",r["direction"]),
    ]

def _expected_r(s, target):
    # conservative fixed-target EV: hit target or lose 1R.
    p=float(s.get(f"hit_{target}r_pct",0))/100.0
    return p*target-(1-p)

def _quality(s):
    if not s or not s.get("triggered"): return 0.0
    e3=_expected_r(s,3); e5=_expected_r(s,5)
    # Favor robust 3R edge while rewarding genuine 5R extension.
    return .65*e3 + .35*e5

def _group(rows, mode):
    g=defaultdict(list)
    for r in rows:
        ks=_parent_keys(r)
        k={"exact":ks[0],"family":ks[1],"market":ks[2],"global":ks[3]}[mode]
        g[k].append(r)
    return {k:_stats(v) for k,v in g.items()}

def _blend(exact, family, market, global_, prior_strength=80.0):
    # Hierarchical empirical-Bayes style shrinkage. Small exact samples borrow strength.
    levels=[(exact,1.0),(family,.55),(market,.30),(global_,.15)]
    weighted=[]; total=0.0
    for s,w in levels:
        if not s: continue
        n=float(s.get("triggered",0))
        if n<=0: continue
        eff=w*n/(n+prior_strength)
        weighted.append((_quality(s),eff,n,s)); total+=eff
    if not weighted:return None
    q=sum(v*w for v,w,_,_ in weighted)/total
    n_exact=int(exact.get("triggered",0)) if exact else 0
    return {"edge":q,"triggered":n_exact,"levels":len(weighted)}

def _tier(edge, n, stability):
    # Deliberately strict. No evidence = no confidence.
    if n < 25:return "INSUFFICIENT_EVIDENCE"
    adj=edge-stability
    if n>=50 and adj>=1.35:return "ELITE"
    if n>=35 and adj>=0.65:return "WATCH"
    if adj>0:return "RESEARCH"
    return "RESEARCH"

def _folds(rows, n_folds=5, final_holdout=.15):
    n=len(rows); final_start=max(1,int(n*(1-final_holdout)))
    dev=rows[:final_start]; final=rows[final_start:]
    fold_size=max(1,len(dev)//(n_folds+1))
    out=[]
    for i in range(1,n_folds+1):
        train_end=fold_size*i
        test_end=min(len(dev),train_end+fold_size)
        if train_end<100 or test_end<=train_end: continue
        out.append((dev[:train_end],dev[train_end:test_end]))
    return out,final,dev

def _maps(train):
    return {m:_group(train,m) for m in ("exact","family","market","global")}

def _lookup(maps,r):
    ks=_parent_keys(r)
    return [maps["exact"].get(ks[0]),maps["family"].get(ks[1]),
            maps["market"].get(ks[2]),maps["global"].get(ks[3])]

def _tier_stats(rows, assignments):
    g=defaultdict(list)
    for r,t in zip(rows,assignments):g[t].append(r)
    return {t:_stats(v) for t,v in g.items()}

def _ordered(stats,target):
    vals=[]
    for t in ("ELITE","WATCH","RESEARCH"):
        if t not in stats or stats[t].get("triggered",0)<10:return None
        vals.append(stats[t].get(f"hit_{target}r_pct",0))
    return vals[0]>=vals[1]>=vals[2]

def optimize(path="research_data/v4/evidence_v3.db", n_folds=5, final_holdout=.15):
    rows,table,time_col=load_ordered(path)
    folds,final,dev=_folds(rows,n_folds,final_holdout)
    history=defaultdict(list); fold_reports=[]
    for idx,(train,test) in enumerate(folds,1):
        maps=_maps(train); assigns=[]
        for r in test:
            exact,family,market,glob=_lookup(maps,r)
            b=_blend(exact,family,market,glob)
            if not b: t="INSUFFICIENT_EVIDENCE"
            else:
                h=history[_key(r)]
                stability=pstdev(h) if len(h)>=2 else .20
                t=_tier(b["edge"],b["triggered"],stability)
                h.append(b["edge"])
            assigns.append(t)
        s=_tier_stats(test,assigns)
        fold_reports.append({"fold":idx,"rows":len(test),"tiers":s,
            "ordered_3r":_ordered(s,3),"ordered_5r":_ordered(s,5)})
    # Freeze model on all development data, then touch final holdout once.
    maps=_maps(dev); assigns=[]; decisions=[]
    for r in final:
        exact,family,market,glob=_lookup(maps,r);b=_blend(exact,family,market,glob)
        stability=pstdev(history[_key(r)]) if len(history[_key(r)])>=2 else .20
        t="INSUFFICIENT_EVIDENCE" if not b else _tier(b["edge"],b["triggered"],stability)
        assigns.append(t)
        decisions.append((t,b["edge"] if b else None))
    fs=_tier_stats(final,assigns)
    # Target policy learned only from development evidence.
    devs=_stats(dev); ev3=_expected_r(devs,3);ev5=_expected_r(devs,5)
    target_policy="5R" if ev5>ev3 else "3R"
    valid=[f for f in fold_reports if f["ordered_3r"] is not None]
    consistency_3=sum(bool(f["ordered_3r"]) for f in valid)/len(valid) if valid else 0
    valid5=[f for f in fold_reports if f["ordered_5r"] is not None]
    consistency_5=sum(bool(f["ordered_5r"]) for f in valid5)/len(valid5) if valid5 else 0
    return {
      "version":"V4_WF_1","table":table,"time_column":time_col,"rows":len(rows),
      "development_rows":len(dev),"final_holdout_rows":len(final),
      "folds":fold_reports,"walkforward_ordering_rate_3r":round(consistency_3,3),
      "walkforward_ordering_rate_5r":round(consistency_5,3),
      "final_holdout":{"tiers":fs,"ordered_3r":_ordered(fs,3),"ordered_5r":_ordered(fs,5)},
      "development_target_ev":{"3R":round(ev3,4),"5R":round(ev5,4)},
      "preferred_fixed_target":target_policy,
      "promotion_ready": bool(_ordered(fs,3)) and consistency_3>=.60,
      "research_only":True
    }
