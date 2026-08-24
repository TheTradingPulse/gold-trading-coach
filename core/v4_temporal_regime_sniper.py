from __future__ import annotations
import json, math, sqlite3
from pathlib import Path
from collections import defaultdict
from datetime import datetime

VERSION="V4_TEMPORAL_REGIME_SNIPER_1"

def wilson_low(k,n,z=1.96):
    if not n: return 0.0
    p=k/n; d=1+z*z/n
    return (p+z*z/(2*n)-z*math.sqrt((p*(1-p)+z*z/(4*n))/n))/d

def ev(p,target_r):
    return p*target_r-(1-p)

def _j(s):
    try: return json.loads(s or "{}")
    except Exception: return {}

def _bucket_rr(v):
    try: v=float(v)
    except: return "UNKNOWN"
    if v < 2: return "<2"
    if v < 3: return "2-3"
    if v < 4: return "3-4"
    if v < 5: return "4-5"
    return "5+"

def _month(ts):
    return str(ts)[:7]

def load_rows(db):
    db=Path(db)
    if not db.exists(): raise FileNotFoundError(db)
    con=sqlite3.connect(db); con.row_factory=sqlite3.Row
    tables=[r[0] for r in con.execute("select name from sqlite_master where type='table'")]
    table="observations" if "observations" in tables else (tables[0] if tables else None)
    if not table: raise RuntimeError("No evidence table found")
    rows=[]
    for r in con.execute(f"select * from {table} order by as_of"):
        x=dict(r); c=_j(x.get("context_json")); cand=_j(x.get("candidate_json"))
        x["session"]=c.get("session_utc") or c.get("session") or "UNKNOWN"
        x["trend_1h"]=c.get("trend_1h") or "UNKNOWN"
        x["trend_4h"]=c.get("trend_4h") or "UNKNOWN"
        x["volatility"]=c.get("volatility_15m") or c.get("volatility_regime") or "UNKNOWN"
        x["rr_bucket"]=_bucket_rr(c.get("projected_rr",cand.get("projected_rr")))
        x["month"]=_month(x.get("as_of"))
        rows.append(x)
    con.close()
    return rows

def stats(rows):
    trig=[r for r in rows if int(r.get("entered") or 0)==1]
    n=len(trig); h3=sum(int(r.get("primary_hit") or 0) for r in trig); h5=sum(int(r.get("stretch_hit") or 0) for r in trig)
    p3=h3/n if n else 0; p5=h5/n if n else 0
    return {"assigned":len(rows),"triggered":n,"hit3":h3,"hit5":h5,
            "p3":round(p3,4) if n else None,"p5":round(p5,4) if n else None,
            "w3":round(wilson_low(h3,n),4) if n else None,"w5":round(wilson_low(h5,n),4) if n else None,
            "ev3":round(ev(p3,3),4) if n else None,"ev5":round(ev(p5,5),4) if n else None}

def _key(r, features):
    return tuple(str(r.get(f,"UNKNOWN")) for f in features)

def discover(train, features, min_triggered=80):
    groups=defaultdict(list)
    for r in train: groups[_key(r,features)].append(r)
    out=[]
    for key,rs in groups.items():
        s=stats(rs)
        if s["triggered"] < min_triggered: continue
        months=defaultdict(list)
        for r in rs: months[r["month"]].append(r)
        ms=[stats(v) for v in months.values()]
        good=[m for m in ms if m["triggered"]>=10]
        if not good: continue
        month_ev3=[m["ev3"] for m in good if m["ev3"] is not None]
        month_ev5=[m["ev5"] for m in good if m["ev5"] is not None]
        pos3=sum(v>0 for v in month_ev3)/len(month_ev3) if month_ev3 else 0
        pos5=sum(v>0 for v in month_ev5)/len(month_ev5) if month_ev5 else 0
        worst3=min(month_ev3) if month_ev3 else -99
        worst5=min(month_ev5) if month_ev5 else -99
        stability=min(pos3,pos5)
        quality=(s["w3"]*3+s["w5"]*5)/2 + stability
        out.append({"features":features,"values":key,"stats":s,"months":len(good),
                    "positive_months_3r":round(pos3,3),"positive_months_5r":round(pos5,3),
                    "worst_month_ev3":round(worst3,3),"worst_month_ev5":round(worst5,3),
                    "stability":round(stability,3),"quality":round(quality,4)})
    return sorted(out,key=lambda x:x["quality"],reverse=True)

def matches(r,rule):
    return _key(r,rule["features"])==tuple(rule["values"])

def evaluate_rules(rows,rules):
    matched=[r for r in rows if any(matches(r,q) for q in rules)]
    return stats(matched)

def prune_redundant(rules, max_rules=30):
    seen=set(); out=[]
    for r in rules:
        sig=(tuple(r["features"]),tuple(r["values"]))
        if sig in seen: continue
        seen.add(sig); out.append(r)
        if len(out)>=max_rules: break
    return out

def choose_target(s):
    if not s or not s.get("triggered"): return "3R"
    # Require meaningful incremental 5R advantage; otherwise bank 3R.
    return "5R" if s["ev5"] is not None and s["ev3"] is not None and s["ev5"] >= s["ev3"]+0.20 and s["w5"]>=0.34 else "3R"

def run(db,out_dir):
    rows=load_rows(db); n=len(rows)
    a=int(n*.50); b=int(n*.70); c=int(n*.85)
    discovery,calibration,validation,holdout=rows[:a],rows[a:b],rows[b:c],rows[c:]
    feature_sets=[
        ("symbol","setup_type","direction"),
        ("symbol","setup_type","direction","session"),
        ("symbol","setup_type","direction","rr_bucket"),
        ("symbol","setup_type","direction","trend_1h"),
        ("symbol","setup_type","direction","trend_4h"),
        ("symbol","setup_type","direction","volatility"),
        ("setup_type","direction","session","rr_bucket"),
        ("symbol","setup_type","direction","session","rr_bucket"),
    ]
    candidates=[]
    for fs in feature_sets: candidates += discover(discovery,fs)
    # Stability-first gates; calibration is used before freezing.
    stable=[]
    for r in candidates:
        if r["stats"]["w3"] < .48 or r["stats"]["w5"] < .30 or r["stability"] < .70 or r["months"] < 3: continue
        cs=evaluate_rules(calibration,[r])
        if cs["triggered"] < 35 or cs["w3"] < .45 or cs["ev3"] < .75: continue
        rr=dict(r); rr["calibration"]=cs; stable.append(rr)
    stable=sorted(stable,key=lambda x:(x["calibration"]["w3"],x["calibration"]["w5"],x["quality"]),reverse=True)
    elite=prune_redundant(stable,30)
    grand=prune_redundant([r for r in stable if r["calibration"]["w3"]>=.58 and r["calibration"]["w5"]>=.40 and r["calibration"]["ev5"]>=1.4],15)
    val_e=evaluate_rules(validation,elite); val_g=evaluate_rules(validation,grand)
    final_e=evaluate_rules(holdout,elite); final_g=evaluate_rules(holdout,grand)
    promotion_elite=bool(final_e["triggered"]>=250 and final_e["w3"]>=.50 and final_e["w5"]>=.34 and final_e["ev3"]>=1.0)
    promotion_grand=bool(final_g["triggered"]>=150 and final_g["w3"]>=.60 and final_g["w5"]>=.45 and final_g["ev5"]>=1.8)
    report={"version":VERSION,"rows":n,"splits":{"discovery":len(discovery),"calibration":len(calibration),"validation":len(validation),"final_holdout":len(holdout)},
            "rules":{"elite":len(elite),"grand_slam":len(grand)},
            "validation":{"elite":val_e,"grand_slam":val_g},
            "final_holdout":{"elite":final_e,"grand_slam":final_g},
            "targets":{"elite":choose_target(final_e),"grand_slam":choose_target(final_g)},
            "promotion":{"elite":promotion_elite,"grand_slam":promotion_grand,
                         "status":"PROMOTION_CANDIDATE" if promotion_elite else "KEEP_RESEARCH_ONLY"},
            "elite_rules":elite,"grand_slam_rules":grand}
    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
    (out/"temporal_regime_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    (out/"frozen_temporal_rules.json").write_text(json.dumps({"version":VERSION,"elite":elite,"grand_slam":grand},indent=2),encoding="utf-8")
    return report
