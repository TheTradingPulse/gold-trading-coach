from __future__ import annotations
import math
import pandas as pd

def wilson_low(hits, n, z=1.96):
    if n <= 0: return None
    p = hits / n
    den = 1 + z*z/n
    center = p + z*z/(2*n)
    adj = z * math.sqrt((p*(1-p) + z*z/(4*n))/n)
    return (center-adj)/den

def max_loss_streak(values):
    best=cur=0
    for v in values:
        if v <= 0: cur += 1; best=max(best,cur)
        else: cur=0
    return best

def summarize(df, target_r=3.0):
    if df is None or len(df)==0:
        return {"trades":0}
    d=df.copy()
    entered = d[d.get("entered", True).astype(bool)] if "entered" in d.columns else d
    n=len(entered)
    if n==0: return {"trades":0}
    hit_col = "primary_hit" if target_r == 3 else "stretch_hit"
    hits=int(entered[hit_col].fillna(False).astype(bool).sum()) if hit_col in entered else 0
    realized=pd.to_numeric(entered.get("realized_r", pd.Series([0]*n,index=entered.index)),errors="coerce").fillna(0)
    wins=int((realized>0).sum()); losses=int((realized<=0).sum())
    gross_win=float(realized[realized>0].sum())
    gross_loss=abs(float(realized[realized<0].sum()))
    return {
        "trades":n, "wins":wins, "losses":losses,
        "hit_pct":round(100*hits/n,2),
        "wilson_low_pct":round(100*wilson_low(hits,n),2),
        "avg_r":round(float(realized.mean()),4),
        "expectancy_r":round(float(realized.mean()),4),
        "profit_factor":round(gross_win/gross_loss,4) if gross_loss else None,
        "max_loss_streak":max_loss_streak(realized.tolist()),
    }

def grouped_metrics(df, dimensions, target_r=3.0):
    rows=[]
    for keys,g in df.groupby(dimensions, dropna=False):
        if not isinstance(keys, tuple): keys=(keys,)
        row=dict(zip(dimensions,keys))
        row.update(summarize(g,target_r))
        rows.append(row)
    return pd.DataFrame(rows)
