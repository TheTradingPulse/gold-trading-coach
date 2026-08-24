from __future__ import annotations
import json, math, sqlite3, hashlib
from pathlib import Path
from collections import defaultdict

VERSION="V4_ELITE_DISCOVERY_NESTED_1"
TIER_ORDER=("RESEARCH","WATCH","ELITE","GRAND_SLAM")

FEATURES=("projected_rr","session_utc","grade","htf_aligned_count","lifecycle",
          "trend_1h","trend_4h","trend_d","zone_quality","reason_room",
          "reason_local_trend","reason_htf","volatility_15m")

def _j(v):
    if isinstance(v,dict): return v
    try:return json.loads(v or "{}")
    except:return {}

def _wilson(h,n,z=1.96):
    if not n:return 0.0
    p=h/n; den=1+z*z/n
    return (p+z*z/(2*n)-z*math.sqrt((p*(1-p)+z*z/(4*n))/n))/den

def _bin(name,v):
    if v is None:return "?"
    if name=="projected_rr":
        try:x=float(v)
        except:return "?"
        for hi,l in [(2,"<2"),(3,"2-3"),(5,"3-5"),(10,"5-10"),(20,"10-20")]:
            if x<hi:return l
        return "20+"
    if name in ("zone_quality","reason_room","reason_local_trend","reason_htf"):
        try:x=float(v)
        except:return str(v)
        if x<3:return "LOW"
        if x<7:return "MID"
        return "HIGH"
    return str(v)

def feat(row):
    c=_j(row.get("context_json"))
    return {k:_bin(k,c.get(k, row.get(k))) for k in FEATURES}

def load(path):
    con=sqlite3.connect(str(path));con.row_factory=sqlite3.Row
    rows=[dict(x) for x in con.execute("SELECT * FROM observations ORDER BY as_of,id")]
    con.close();return rows

def split4(rows):
    # Chronological 50/20/15/15: discovery, calibration, validation, final untouched holdout.
    n=len(rows); a=int(n*.50); b=int(n*.70); c=int(n*.85)
    return rows[:a],rows[a:b],rows[b:c],rows[c:]

def outcome_stats(rows):
    t=[r for r in rows if int(r.get("entered") or 0)]
    n=len(t); h3=sum(bool(r.get("primary_hit")) for r in t);h5=sum(bool(r.get("stretch_hit")) for r in t)
    p3=h3/n if n else 0;p5=h5/n if n else 0
    return {"assigned":len(rows),"triggered":n,"hit3":h3,"hit5":h5,
      "p3":p3,"p5":p5,"w3":_wilson(h3,n),"w5":_wilson(h5,n),
      "ev3":4*p3-1 if n else None,"ev5":6*p5-1 if n else None}

def keys_for(row):
    f=feat(row); base=(row.get("symbol"),(row.get("setup_type") or "").lower(),(row.get("direction") or "").upper())
    out=[]
    # single contextual edges + carefully limited pairs; avoids combinatorial overfit.
    for x in FEATURES: out.append((base,(x,f[x])))
    pairs=(("projected_rr","reason_room"),("projected_rr","trend_1h"),("projected_rr","trend_4h"),
           ("projected_rr","htf_aligned_count"),("reason_room","trend_1h"),("lifecycle","trend_1h"),
           ("grade","projected_rr"),("session_utc","trend_1h"))
    for x,y in pairs:out.append((base,(x,f[x]),(y,f[y])))
    return out

def discover(rows,min_trig=45):
    groups=defaultdict(list)
    for r in rows:
        for k in keys_for(r):groups[k].append(r)
    cand=[]
    for k,rs in groups.items():
        s=outcome_stats(rs)
        if s["triggered"]<min_trig:continue
        quality=10*(.45*s["w3"]+.35*s["w5"]+.10*max(0,min(1,(s["ev3"] or 0)/2))+.10*max(0,min(1,(s["ev5"] or 0)/3)))
        cand.append({"key":k,"stats":s,"quality":quality})
    return sorted(cand,key=lambda x:(x["quality"],x["stats"]["triggered"]),reverse=True)

def matches(row,key):
    f=feat(row);base=(row.get("symbol"),(row.get("setup_type") or "").lower(),(row.get("direction") or "").upper())
    if base!=tuple(key[0]):return False
    for part in key[1:]:
        if f.get(part[0])!=part[1]:return False
    return True

def evaluate_rules(rows,rules):
    chosen=[r for r in rows if any(matches(r,x["key"]) for x in rules)]
    return outcome_stats(chosen),chosen

def select(discovery,calibration):
    # Candidate rule must be strong in discovery AND survive later calibration.
    pool=discover(discovery)
    elite=[]; grand=[]
    for c in pool[:500]:
        rs=[r for r in calibration if matches(r,c["key"])]
        s=outcome_stats(rs)
        if s["triggered"]<30:continue
        stable3=abs(s["p3"]-c["stats"]["p3"])<=.18
        stable5=abs(s["p5"]-c["stats"]["p5"])<=.18
        if stable3 and stable5 and s["w3"]>=.50 and s["w5"]>=.32 and (s["ev3"] or -9)>=1.0:
            elite.append({"key":c["key"],"discovery":c["stats"],"calibration":s})
        if stable3 and stable5 and s["triggered"]>=35 and s["w3"]>=.62 and s["w5"]>=.48 and (s["ev5"] or -9)>=2.0:
            grand.append({"key":c["key"],"discovery":c["stats"],"calibration":s})
    # De-duplicate exact keys.
    return elite[:100],grand[:50]

def validate(path,outdir="research_data/v4/elite_discovery_nested"):
    rows=load(path);d,c,v,h=split4(rows)
    elite,grand=select(d,c)
    ev,_=evaluate_rules(v,elite); gv,_=evaluate_rules(v,grand)
    # Freeze rules before touching final holdout.
    elite_pass=ev["triggered"]>=30 and ev["w3"]>=.50 and ev["w5"]>=.32 and (ev["ev3"] or -9)>=1.0
    grand_pass=gv["triggered"]>=20 and gv["w3"]>=.62 and gv["w5"]>=.48 and (gv["ev5"] or -9)>=2.0
    frozen_elite=elite if elite_pass else []
    frozen_grand=grand if grand_pass else []
    eh,_=evaluate_rules(h,frozen_elite); gh,_=evaluate_rules(h,frozen_grand)
    final_elite=eh["triggered"]>=25 and eh["w3"]>=.48 and eh["w5"]>=.30 and (eh["ev3"] or -9)>=.9
    final_grand=gh["triggered"]>=15 and gh["w3"]>=.58 and gh["w5"]>=.44 and (gh["ev5"] or -9)>=1.8
    promotion=bool(final_elite and (not frozen_grand or final_grand))
    report={"version":VERSION,"rows":len(rows),"splits":{"discovery":len(d),"calibration":len(c),"validation":len(v),"final_holdout":len(h)},
      "elite_rules_discovered":len(elite),"grandslam_rules_discovered":len(grand),
      "validation":{"elite":ev,"grandslam":gv,"elite_pass":elite_pass,"grandslam_pass":grand_pass},
      "final_holdout":{"elite":eh,"grandslam":gh,"elite_pass":final_elite,"grandslam_pass":final_grand},
      "promotion_ready":promotion,"promotion_status":"PROMOTION_CANDIDATE" if promotion else "KEEP_RESEARCH_ONLY",
      "frozen_elite_rules":frozen_elite,"frozen_grandslam_rules":frozen_grand}
    p=Path(outdir);p.mkdir(parents=True,exist_ok=True)
    (p/"nested_validation_report.json").write_text(json.dumps(report,indent=2,default=str),encoding="utf-8")
    (p/"frozen_rules.json").write_text(json.dumps({"elite":frozen_elite,"grandslam":frozen_grand},indent=2,default=str),encoding="utf-8")
    return report
