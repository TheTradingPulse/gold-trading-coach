from __future__ import annotations
import json, math, sqlite3
from collections import defaultdict
from pathlib import Path

from v4_grandslam_policy import decide_grandslam

VERSION = "V4_GRANDSLAM_OOS_1"
TIER_ORDER = ["RESEARCH","WATCH","ELITE","GRAND_SLAM"]

def _j(v):
    if isinstance(v, dict): return v
    try: return json.loads(v or "{}")
    except Exception: return {}

def _bucket(v, cuts):
    try: x=float(v)
    except Exception: return "?"
    for label, hi in cuts:
        if x < hi: return label
    return cuts[-1][0] + "+"

RR_CUTS=[("<2",2),("2-3",3),("3-5",5),("5-10",10),("10-20",20),("20+",1e99)]
ROOM_CUTS=[("<2R",2),("2-3R",3),("3-5R",5),("5-10R",10),("10R+",1e99)]

def _norm_dir(row, ctx):
    d=(row.get("direction") or ctx.get("direction") or "").upper()
    return d if d in ("LONG","SHORT") else "?"

def _feature(row):
    c=_j(row.get("context_json"))
    rr=c.get("projected_rr")
    room_r=None
    try:
        risk=float(c.get("risk_points") or 0)
        room=float(c.get("opposing_room_points"))
        if risk>0: room_r=room/risk
    except Exception: pass
    return {
      "symbol":row.get("symbol"),
      "setup_type":(row.get("setup_type") or "").lower(),
      "direction":_norm_dir(row,c),
      "session":c.get("session_utc"),
      "trend1":c.get("trend_1h"),
      "trend4":c.get("trend_4h"),
      "trendd":c.get("trend_d"),
      "life":c.get("lifecycle") or row.get("lifecycle"),
      "grade":c.get("grade") or row.get("grade"),
      "rr":_bucket(rr,RR_CUTS),
      "room":_bucket(room_r,ROOM_CUTS),
      "htf":str(c.get("htf_aligned_count","?")),
      "complete":float(c.get("feature_completeness") or 0),
      "projected_rr":rr,
      "actionable":bool(c.get("is_actionable", row.get("entered",0))),
    }

LEVELS = [
 ("L0", ("symbol","setup_type","direction","session","trend1","trend4","life","rr","htf"), .93),
 ("L1", ("symbol","setup_type","direction","session","trend1","trend4","rr","htf"), .89),
 ("L2", ("symbol","setup_type","direction","trend1","trend4","rr","htf"), .85),
 ("L3", ("symbol","setup_type","direction","trend1","trend4","rr"), .81),
 ("L4", ("symbol","setup_type","direction","rr"), .77),
 ("L5", ("symbol","setup_type","direction"), .73),
]

def _key(f, fields): return tuple(f.get(x) for x in fields)

def _stats_new():
    return {"n":0,"triggered":0,"hit_3r":0,"hit_5r":0}

def _add(s,row):
    s["n"]+=1
    if int(row.get("entered") or 0):
        s["triggered"]+=1
        s["hit_3r"]+=int(bool(row.get("primary_hit")))
        s["hit_5r"]+=int(bool(row.get("stretch_hit")))

def load_rows(path):
    con=sqlite3.connect(str(path)); con.row_factory=sqlite3.Row
    cols={r[1] for r in con.execute("PRAGMA table_info(observations)")}
    need={"symbol","as_of","setup_type","direction","entered","primary_hit","stretch_hit","context_json"}
    miss=need-cols
    if miss: raise RuntimeError("Evidence V4 missing columns: "+", ".join(sorted(miss)))
    rows=[dict(r) for r in con.execute("SELECT * FROM observations ORDER BY as_of,id")]
    con.close()
    return rows

def split_rows(rows, train_fraction=.70):
    if not rows: return [],[]
    i=max(1,min(len(rows)-1,int(len(rows)*train_fraction)))
    return rows[:i],rows[i:]

def build_index(train):
    idx={name:defaultdict(_stats_new) for name,_,_ in LEVELS}
    for r in train:
        f=_feature(r)
        for name,fields,_ in LEVELS:
            _add(idx[name][_key(f,fields)],r)
    return idx

def classify(row, idx):
    f=_feature(row)
    selected=None; level=None; sim=0
    for name,fields,s in LEVELS:
        z=idx[name].get(_key(f,fields))
        if z and z["triggered"]>=40:
            selected=dict(z); level=name; sim=s; break
    if selected is None:
        selected={"n":0,"triggered":0,"hit_3r":0,"hit_5r":0}
    d=decide_grandslam(selected, completeness=f["complete"], mean_similarity=sim,
                       projected_rr=f["projected_rr"], actionable=f["actionable"])
    d["analogue_level"]=level
    return d

def _metric(rows):
    n=len(rows); trig=[r for r in rows if int(r["entered"] or 0)]
    t=len(trig); h3=sum(int(bool(r["primary_hit"])) for r in trig); h5=sum(int(bool(r["stretch_hit"])) for r in trig)
    # Fixed-target EV: winner receives target R, all other triggered trades conservatively count -1R.
    ev3=(h3*3-(t-h3))/t if t else None
    ev5=(h5*5-(t-h5))/t if t else None
    return {"assigned":n,"triggered":t,
      "trigger_pct":round(100*t/n,2) if n else 0,
      "hit_3r":h3,"hit_5r":h5,
      "hit_3r_pct":round(100*h3/t,2) if t else None,
      "hit_5r_pct":round(100*h5/t,2) if t else None,
      "realized_ev_3r":round(ev3,4) if ev3 is not None else None,
      "realized_ev_5r":round(ev5,4) if ev5 is not None else None}

def _ordered(summary, metric):
    vals=[]
    for t in TIER_ORDER:
        x=summary.get(t,{}).get(metric)
        if x is not None and summary.get(t,{}).get("triggered",0)>=20: vals.append((t,x))
    return len(vals)>=2 and all(vals[i][1] <= vals[i+1][1] for i in range(len(vals)-1))

def validate(path="research_data/v4/context_evidence_v4.db", train_fraction=.70, output=None):
    rows=load_rows(path); train,oos=split_rows(rows,train_fraction)
    idx=build_index(train)
    assigned=defaultdict(list); by_market=defaultdict(lambda:defaultdict(list)); examples=defaultdict(list)
    false_elites=[]
    for r in oos:
        d=classify(r,idx); tier=d["tier"]
        if tier=="INSUFFICIENT_EVIDENCE": tier="RESEARCH"
        assigned[tier].append(r); by_market[r["symbol"]][tier].append(r)
        if tier in ("ELITE","GRAND_SLAM") and len(examples[tier])<30:
            examples[tier].append({"symbol":r["symbol"],"as_of":r["as_of"],"setup_type":r["setup_type"],
              "direction":r["direction"],"score10":r.get("score10"),"entered":bool(r["entered"]),
              "hit_3r":bool(r["primary_hit"]),"hit_5r":bool(r["stretch_hit"]),"decision":d})
        if tier in ("ELITE","GRAND_SLAM") and int(r["entered"] or 0) and not bool(r["primary_hit"]):
            if len(false_elites)<100:
                false_elites.append({"tier":tier,"symbol":r["symbol"],"as_of":r["as_of"],
                  "setup_type":r["setup_type"],"direction":r["direction"],"score10":r.get("score10"),"decision":d})
    summary={t:_metric(assigned[t]) for t in TIER_ORDER}
    markets={m:{t:_metric(x[t]) for t in TIER_ORDER} for m,x in sorted(by_market.items())}
    ordered3=_ordered(summary,"hit_3r_pct"); ordered5=_ordered(summary,"hit_5r_pct")
    elite=summary["ELITE"]; gs=summary["GRAND_SLAM"]
    elite_ok=elite["triggered"]>=30 and (elite["hit_3r_pct"] or 0)>=55 and (elite["realized_ev_3r"] or -99)>=1.20
    gs_present=gs["triggered"]>=20
    gs_ok=(not gs_present) or ((gs["hit_3r_pct"] or 0)>=70 and (gs["hit_5r_pct"] or 0)>=55 and
                               (gs["realized_ev_5r"] or -99)>=2.30)
    promotion=bool(ordered3 and elite_ok and gs_ok)
    report={"version":VERSION,"database":str(path),"rows":len(rows),"train_rows":len(train),"oos_rows":len(oos),
      "train_fraction":train_fraction,"strict_time_split":True,"no_oos_labels_used_for_tiering":True,
      "tiers":summary,"by_market":markets,"ordered_3r":ordered3,"ordered_5r":ordered5,
      "elite_gate_pass":elite_ok,"grandslam_has_adequate_oos_sample":gs_present,
      "grandslam_gate_pass":gs_ok,"promotion_ready":promotion,
      "promotion_status":"PROMOTION_CANDIDATE" if promotion else "KEEP_RESEARCH_ONLY",
      "elite_examples":examples["ELITE"],"grandslam_examples":examples["GRAND_SLAM"],
      "false_elite_examples":false_elites}
    if output:
        p=Path(output); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(report,indent=2,default=str),encoding="utf-8")
    return report
