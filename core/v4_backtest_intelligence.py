from __future__ import annotations
import json,sqlite3,math
from pathlib import Path

def wilson_low(hits,n,z=1.96):
    if not n:return None
    p=hits/n;den=1+z*z/n;center=p+z*z/(2*n);adj=z*math.sqrt((p*(1-p)+z*z/(4*n))/n)
    return (center-adj)/den

def _cols(con,table):return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
def _pick(cols,*names):return next((n for n in names if n in cols),None)

def evidence_metrics(path="research_data/v4/context_evidence_v4.db",filters=None):
    p=Path(path)
    if not p.exists():return {"available":False,"path":str(p),"reason":"database not found"}
    filters=filters or {}
    with sqlite3.connect(p) as con:
        con.row_factory=sqlite3.Row;cols=_cols(con,"observations")
        where=[];args=[]
        for key in ("symbol","setup_type","direction","grade","lifecycle"):
            if key in filters and key in cols:where.append(f"{key}=?");args.append(filters[key])
        if "start" in filters and "as_of" in cols:where.append("as_of>=?");args.append(filters["start"])
        if "end" in filters and "as_of" in cols:where.append("as_of<=?");args.append(filters["end"])
        W=(" WHERE "+" AND ".join(where)) if where else ""
        row=dict(con.execute(f"SELECT COUNT(*) observations,COALESCE(SUM(entered),0) triggered,COALESCE(SUM(primary_hit),0) hit_3r,COALESCE(SUM(stretch_hit),0) hit_5r,COALESCE(SUM(stop_hit),0) stops,AVG(CASE WHEN entered=1 THEN realized_r END) avg_realized_r,AVG(CASE WHEN entered=1 THEN mfe_r END) avg_mfe_r,AVG(CASE WHEN entered=1 THEN mae_r END) avg_mae_r FROM observations{W}",args).fetchone())
        n=int(row["triggered"] or 0);h3=int(row["hit_3r"] or 0);h5=int(row["hit_5r"] or 0)
        row.update({"trigger_pct":round(100*n/row["observations"],2) if row["observations"] else None,"hit_3r_pct":round(100*h3/n,2) if n else None,"hit_5r_pct":round(100*h5/n,2) if n else None,"wilson_3r_low_pct":round(100*wilson_low(h3,n),2) if n else None,"wilson_5r_low_pct":round(100*wilson_low(h5,n),2) if n else None,"ev_3r":round(4*h3/n-1,4) if n else None,"ev_5r":round(6*h5/n-1,4) if n else None})
        groups={}
        for g in ("symbol","setup_type","direction","grade","lifecycle","replay_timeframe"):
            if g not in cols:continue
            groups[g]=[dict(r) for r in con.execute(f"SELECT {g} value,COUNT(*) observations,SUM(entered) triggered,SUM(primary_hit) hit_3r,SUM(stretch_hit) hit_5r,AVG(CASE WHEN entered=1 THEN realized_r END) avg_realized_r FROM observations{W} GROUP BY {g} ORDER BY triggered DESC",args)]
    return {"available":True,"path":str(p),"filters":filters,"summary":row,"breakdowns":groups}

def research_artifacts(root="research_data/v4"):
    root=Path(root);out=[]
    for p in root.rglob("*.json") if root.exists() else []:
        low=str(p).lower();label="research"
        if "holdout" in low:label="holdout"
        elif "validation" in low or "oos" in low:label="validation"
        elif "blind" in low:label="blind"
        out.append({"path":str(p),"label":label,"bytes":p.stat().st_size,"modified":p.stat().st_mtime})
    return sorted(out,key=lambda x:x["modified"],reverse=True)
