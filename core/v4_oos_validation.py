from __future__ import annotations
import json, math, sqlite3
from pathlib import Path
from collections import defaultdict
from v4_calibration_engine import normalize, _table, _stats, empirical_quality, score_bucket

def _time_col(cols):
    m={c.lower():c for c in cols}
    for n in ("as_of","asof","timestamp","event_time","created_at","ts"):
        if n in m:return m[n]
    return None

def load_ordered(path):
    path=Path(path)
    if not path.exists() or path.stat().st_size<=0:
        raise RuntimeError(f"Evidence DB missing/empty: {path}")
    conn=sqlite3.connect(path);conn.row_factory=sqlite3.Row
    try:
        table,cols=_table(conn);tc=_time_col(cols)
        order=f' ORDER BY "{tc}"' if tc else " ORDER BY rowid"
        raw=[dict(r) for r in conn.execute(f'SELECT * FROM "{table}"{order}')]
        rows=normalize(raw,cols)
        return rows,table,tc
    finally:conn.close()

def _key(r):
    return (r["symbol"],r["setup_type"],r["direction"],score_bucket(r["score10"]))

def build_train_map(rows,min_triggered=25):
    g=defaultdict(list)
    for r in rows:g[_key(r)].append(r)
    out={}
    for k,rs in g.items():
        s=_stats(rs)
        if s["triggered"]>=min_triggered:
            out[k]={**s,"evidence_quality10":empirical_quality(s)}
    return out

def tier_for(g):
    if not g:return "INSUFFICIENT_EVIDENCE"
    q=float(g["evidence_quality10"]);n=int(g["triggered"])
    if q>=6 and n>=30:return "ELITE"
    if q>=4 and n>=25:return "WATCH"
    return "RESEARCH"

def evaluate_oos(path="research_data/v4/evidence_v3.db",train_fraction=.70,min_triggered=25):
    rows,table,time_col=load_ordered(path)
    cut=max(1,min(len(rows)-1,int(len(rows)*train_fraction)))
    train,test=rows[:cut],rows[cut:]
    tm=build_train_map(train,min_triggered)
    buckets=defaultdict(list)
    for r in test:
        g=tm.get(_key(r));t=tier_for(g);buckets[t].append(r)
    result={}
    for tier,rs in buckets.items():
        result[tier]=_stats(rs)
    def p3(t):return result.get(t,{}).get("hit_3r_pct",0)
    def p5(t):return result.get(t,{}).get("hit_5r_pct",0)
    ordered_3r=p3("ELITE")>=p3("WATCH")>=p3("RESEARCH") if all(x in result for x in ("ELITE","WATCH","RESEARCH")) else None
    ordered_5r=p5("ELITE")>=p5("WATCH")>=p5("RESEARCH") if all(x in result for x in ("ELITE","WATCH","RESEARCH")) else None
    return {
      "version":"V4_OOS_1","rows":len(rows),"train_rows":len(train),"test_rows":len(test),
      "train_fraction":train_fraction,"table":table,"time_column":time_col,
      "tier_results":result,"ordered_3r":ordered_3r,"ordered_5r":ordered_5r,
      "passes_ordering": bool(ordered_3r and ordered_5r) if ordered_3r is not None and ordered_5r is not None else False
    }
