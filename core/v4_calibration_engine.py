from __future__ import annotations
import json, math, sqlite3
from pathlib import Path
from collections import defaultdict

BUCKETS=((0,6,"<6"),(6,7,"6-6.9"),(7,8,"7-7.9"),(8,8.5,"8-8.4"),(8.5,9,"8.5-8.9"),(9,10.01,"9+"))

def _f(v, d=None):
    try:
        x=float(v)
        return x if math.isfinite(x) else d
    except Exception:
        return d

def score_bucket(x):
    x=_f(x,0.0)
    for lo,hi,name in BUCKETS:
        if lo <= x < hi: return name
    return "9+" if x >= 9 else "<6"

def wilson(hits,n,z=1.96):
    if not n: return 0.0,0.0
    p=hits/n; den=1+z*z/n
    ctr=(p+z*z/(2*n))/den
    rad=z*math.sqrt((p*(1-p)+z*z/(4*n))/n)/den
    return max(0,ctr-rad),min(1,ctr+rad)

def _table(conn):
    rows=conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names=[r[0] for r in rows]
    preferred=[n for n in names if "evidence" in n.lower()]
    for n in preferred+names:
        cols=[r[1] for r in conn.execute(f'PRAGMA table_info("{n}")')]
        low={c.lower() for c in cols}
        if {"symbol","primary_hit","stretch_hit"}.issubset(low):
            return n, cols
    raise RuntimeError("No Evidence V3-compatible table found.")

def _col(cols,*names):
    m={c.lower():c for c in cols}
    for n in names:
        if n.lower() in m:return m[n.lower()]
    return None

def load_rows(path):
    conn=sqlite3.connect(path); conn.row_factory=sqlite3.Row
    try:
        table,cols=_table(conn)
        return [dict(r) for r in conn.execute(f'SELECT * FROM "{table}"')], table, cols
    finally: conn.close()

def normalize(rows, cols):
    out=[]
    for r in rows:
        def g(*n):
            c=_col(cols,*n); return r.get(c) if c else None
        score=_f(g("score10","score_10","display_score"))
        if score is None:
            raw=_f(g("score","raw_score","setup_score"),0)
            score=raw/10 if raw>10 else raw
        out.append({
            "symbol":str(g("symbol") or "").upper(),
            "setup_type":str(g("setup_type","zone_type","type") or "UNKNOWN").lower(),
            "direction":str(g("direction","side") or "UNKNOWN").upper(),
            "score10":max(0,min(10,score or 0)),
            "entered":int(bool(g("entered","triggered"))),
            "hit3":int(bool(g("primary_hit","hit_3r"))),
            "hit5":int(bool(g("stretch_hit","hit_5r"))),
            "mfe":_f(g("alive_mfe_r","mfe_r","research_achieved_r"),0),
            "mae":_f(g("alive_mae_r","mae_r"),0),
            "risk":_f(g("risk_width","risk","risk_distance")),
        })
    return out

def _stats(rows):
    n=len(rows); trig=[r for r in rows if r["entered"]]
    nt=len(trig); h3=sum(r["hit3"] for r in trig); h5=sum(r["hit5"] for r in trig)
    lo3,hi3=wilson(h3,nt); lo5,hi5=wilson(h5,nt)
    return {
        "n":n,"triggered":nt,"trigger_pct":round(100*nt/n,2) if n else 0,
        "hit_3r":h3,"hit_5r":h5,
        "hit_3r_pct":round(100*h3/nt,2) if nt else 0,
        "hit_5r_pct":round(100*h5/nt,2) if nt else 0,
        "wilson_3r_low":round(100*lo3,2),"wilson_5r_low":round(100*lo5,2),
        "avg_mfe_r":round(sum(r["mfe"] for r in trig)/nt,3) if nt else None,
        "avg_mae_r":round(sum(r["mae"] for r in trig)/nt,3) if nt else None,
    }

def _group(rows, keys):
    d=defaultdict(list)
    for r in rows:d[tuple(r[k] for k in keys)].append(r)
    return d

def empirical_quality(s):
    # Conservative evidence quality: reward 3R/5R lower confidence bounds,
    # with 3R primary and 5R secondary. Trigger frequency is NOT treated as win quality.
    return round(min(10,max(0, 10*(0.62*(s["wilson_3r_low"]/100)+0.38*(s["wilson_5r_low"]/100)))),3)

def calibrate(path="research_data/v4/evidence_v3.db", min_triggered=25):
    path=Path(path)
    if not path.exists():
        raise RuntimeError(f"Evidence database not found: {path}")
    if path.stat().st_size == 0:
        raise RuntimeError(f"Evidence database is empty: {path}")
    raw,table,cols=load_rows(path); rows=normalize(raw,cols)
    groups=[]
    for keys in (("symbol","setup_type","direction"),("symbol","setup_type","direction","bucket")):
        prepared=[]
        for r in rows:
            q=dict(r);q["bucket"]=score_bucket(q["score10"]);prepared.append(q)
        for k,rs in _group(prepared,keys).items():
            s=_stats(rs); rec={keys[i]:k[i] for i in range(len(keys))};rec.update(s)
            rec["evidence_quality10"]=empirical_quality(s) if s["triggered"]>=min_triggered else None
            rec["sample_ok"]=s["triggered"]>=min_triggered
            groups.append(rec)
    # Score calibration by bucket, used to test monotonicity rather than assume it.
    bucket_stats={}
    prepared=[]
    for r in rows:
        q=dict(r);q["bucket"]=score_bucket(q["score10"]);prepared.append(q)
    for b,rs in _group(prepared,("bucket",)).items():
        s=_stats(rs); bucket_stats[b[0]]=s
    order=["<6","6-6.9","7-7.9","8-8.4","8.5-8.9","9+"]
    monotonic=True; prev=-1
    for b in order:
        v=bucket_stats.get(b,{}).get("wilson_3r_low",0)
        if v+1e-9<prev: monotonic=False
        prev=v
    return {
        "version":"V4_CAL_1",
        "source_db":str(path),"source_table":table,"rows":len(rows),
        "principles":{
            "primary_target_r":3.0,"stretch_target_r":5.0,
            "stop_floor_r":-1.0,
            "live_v3_4_untouched":True,
            "no_lookahead":True,
            "score_policy":"empirical evidence overlay; never promote on raw score alone"
        },
        "bucket_stats":bucket_stats,
        "score_monotonic":monotonic,
        "groups":groups,
    }

def save_calibration(report,out="research_data/v4_calibration.json"):
    p=Path(out);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(report,indent=2),encoding="utf-8")
    return p

class CalibratedScorer:
    def __init__(self, report):
        self.report=report
        self.groups=report.get("groups",[])
    def score(self,symbol,setup_type,direction,raw_score10):
        symbol=symbol.upper();setup_type=setup_type.lower();direction=direction.upper()
        bucket=score_bucket(raw_score10)
        exact=[g for g in self.groups if g.get("symbol")==symbol and g.get("setup_type")==setup_type
               and g.get("direction")==direction and g.get("bucket")==bucket and g.get("sample_ok")]
        broad=[g for g in self.groups if g.get("symbol")==symbol and g.get("setup_type")==setup_type
               and g.get("direction")==direction and "bucket" not in g and g.get("sample_ok")]
        g=(exact or broad)
        evidence=g[0]["evidence_quality10"] if g else None
        # Raw setup score remains a feature; empirical evidence is the majority vote.
        final=raw_score10 if evidence is None else 0.35*float(raw_score10)+0.65*float(evidence)
        final=max(0,min(10,final))
        tier="ELITE" if final>=9 else ("WATCH" if final>=8.5 else "RESEARCH")
        return {"raw_score10":round(float(raw_score10),3),"evidence_score10":evidence,
                "calibrated_score10":round(final,3),"tier":tier,"bucket":bucket,
                "evidence_group":g[0] if g else None}
