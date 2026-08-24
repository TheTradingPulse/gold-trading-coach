from __future__ import annotations

import argparse
import itertools
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


def wilson(w, n, z=1.959963984540054):
    if not n: return None
    p=w/n; d=1+z*z/n
    return (p+z*z/(2*n)-z*math.sqrt((p*(1-p)+z*z/(4*n))/n))/d


def metrics(x):
    n=len(x); w=int(x.win.sum()) if n else 0; p=w/n if n else None
    return {"n":n,"wins":w,"rate":p,"wilson_lower":wilson(w,n),
            "gross_expectancy_r":(4*p-1) if p is not None else None,
            "expectancy_after_0_05r_cost":(4*p-1-.05) if p is not None else None}


def count_metrics(mask, wins):
    n=int(np.count_nonzero(mask));w=int(np.count_nonzero(wins[mask])) if n else 0;p=w/n if n else None
    return {"n":n,"wins":w,"rate":p,"wilson_lower":wilson(w,n),
            "gross_expectancy_r":(4*p-1) if p is not None else None,
            "expectancy_after_0_05r_cost":(4*p-1-.05) if p is not None else None}


def period(year):
    return np.where(year<=2023,"development",np.where(year==2024,"calibration",np.where(year==2025,"holdout","outside")))


def grouped(df, columns):
    rows=[]
    for keys,g in df.groupby(columns,dropna=False,observed=True):
        keys=keys if isinstance(keys,tuple) else (keys,)
        row={c:(str(v) if pd.isna(v) else v) for c,v in zip(columns,keys)};row.update(metrics(g));rows.append(row)
    return pd.DataFrame(rows)


def rule_mask(df,r):
    m=(df.departure_strength>=r["departure_min"])&(df.base_body_ratio<=r["base_body_max"])
    m &= (df.risk_daily_atr>=r["risk_atr_min"])&(df.risk_daily_atr<=r["risk_atr_max"])
    m &= df.risk_ticks>=r["risk_ticks_min"]
    if r["trend_aligned_only"]:m &= df.trend_aligned.eq(1)
    if r["direction"]!="BOTH":m &= df.direction.eq(r["direction"])
    return m


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--root",default=".");a=ap.parse_args();root=Path(a.root).resolve()
    db=root/"research_data/v5/replay_point_in_time/databento_v5_evidence_point_in_time.db";out=root/"research_data/v5/calibration_point_in_time"
    if not db.exists():raise SystemExit(f"Evidence DB missing: {db}")
    out.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(db)
    q="""SELECT candidate_id,symbol,detected_at,direction,risk_ticks,risk_daily_atr,
    departure_strength,base_body_ratio,trend_known,trend_aligned,execution_eligible,
    execution_reason,outcome FROM candidates"""
    df=pd.read_sql_query(q,con); integrity=con.execute("PRAGMA integrity_check").fetchone()[0];con.close()
    df["detected_at"]=pd.to_datetime(df.detected_at,utc=True,errors="coerce");df["year"]=df.detected_at.dt.year
    df["period"]=period(df.year);df["win"]=df.outcome.eq("target_3r_first").astype(int)
    eligible=df[df.execution_eligible.eq(1)].copy()
    # Conservative production view: an unresolved same-minute stop/target order
    # is not allowed to become a verified win.
    resolved=eligible[eligible.outcome.isin(["stop_first","target_3r_first","same_minute_ambiguous"])].copy()
    resolved=resolved[resolved.period.ne("outside")].copy()

    if resolved.empty:raise SystemExit("No eligible resolved 2021-2025 outcomes were found")

    resolved["risk_atr_band"]=pd.cut(resolved.risk_daily_atr,[0,.02,.03,.05,.08,.12,.18,.25,.35,np.inf],right=False)
    resolved["risk_tick_band"]=pd.cut(resolved.risk_ticks,[0,4,8,12,20,40,80,np.inf],right=False)
    resolved["departure_band"]=pd.cut(resolved.departure_strength,[0,1,1.2,1.4,1.6,1.8,2.01],right=False)
    resolved["base_body_band"]=pd.cut(resolved.base_body_ratio,[0,.1,.2,.3,.4,.5,.56],right=False)

    audits={
      "year_symbol":grouped(resolved,["period","year","symbol"]),
      "symbol_direction":grouped(resolved,["period","symbol","direction"]),
      "risk_atr":grouped(resolved,["period","risk_atr_band"]),
      "risk_ticks":grouped(resolved,["period","symbol","risk_tick_band"]),
      "departure":grouped(resolved,["period","departure_band"]),
      "base_body":grouped(resolved,["period","base_body_band"]),
      "trend":grouped(resolved,["period","trend_known","trend_aligned"]),
    }
    for name,x in audits.items():x.to_csv(out/f"audit_{name}.csv",index=False)

    print("Phase 1/3 complete: evidence loaded and descriptive audits written",flush=True)
    arrays={c:resolved[c].to_numpy() for c in
      ("departure_strength","base_body_ratio","risk_daily_atr","risk_ticks","trend_aligned","direction","period","win")}
    period_masks={p:arrays["period"]==p for p in ("development","calibration","holdout")}
    grid=[]
    combos=itertools.product([1.0,1.2,1.4,1.6,1.8],[.15,.25,.35,.45,.55],
      [.015,.03,.05,.08],[.08,.12,.18,.25,.35],[4,8,12,20],[False,True],["BOTH","LONG","SHORT"])
    for rule_number,(dep,body,rmin,rmax,ticks,trend,direction) in enumerate(combos,1):
        if rmin>=rmax:continue
        r={"departure_min":dep,"base_body_max":body,"risk_atr_min":rmin,"risk_atr_max":rmax,
           "risk_ticks_min":ticks,"trend_aligned_only":trend,"direction":direction}
        m=(arrays["departure_strength"]>=dep)&(arrays["base_body_ratio"]<=body)
        m &= (arrays["risk_daily_atr"]>=rmin)&(arrays["risk_daily_atr"]<=rmax)&(arrays["risk_ticks"]>=ticks)
        if trend:m &= arrays["trend_aligned"]==1
        if direction!="BOTH":m &= arrays["direction"]==direction
        row=dict(r)
        for p in ("development","calibration","holdout"):
            mm=count_metrics(m&period_masks[p],arrays["win"])
            row.update({f"{p}_{k}":v for k,v in mm.items()})
        # Selection score never sees holdout outcomes.
        cal_lo=row["calibration_wilson_lower"] or 0;dev_lo=row["development_wilson_lower"] or 0
        row["selection_score"]=min(cal_lo,dev_lo)-abs((row["calibration_rate"] or 0)-(row["development_rate"] or 0))*.25
        row["eligible_for_selection"]=row["development_n"]>=500 and row["calibration_n"]>=200
        grid.append(row)
        if rule_number%2000==0:print(f"  evaluated {rule_number:,} threshold combinations",flush=True)
    rules=pd.DataFrame(grid)
    selected=rules[rules.eligible_for_selection].sort_values(["selection_score","calibration_n"],ascending=[False,False]).head(50).copy()
    selected["holdout_pass_65"]=(selected.holdout_n>=200)&(selected.holdout_wilson_lower>=.65)
    selected["holdout_positive_after_cost"]=(selected.holdout_n>=200)&(selected.holdout_rate>=.2625)
    rules.to_csv(out/"all_candidate_rules.csv",index=False);selected.to_csv(out/"top_preselected_rules_with_holdout.csv",index=False)
    print("Phase 2/3 complete: chronological rule grid evaluated",flush=True)

    baselines={p:metrics(resolved[resolved.period.eq(p)]) for p in ("development","calibration","holdout")}
    best=selected.iloc[0].replace({np.nan:None}).to_dict() if len(selected) else None
    report={"schema":"TP_V5_POINT_IN_TIME_CHRONOLOGICAL_CALIBRATION_2","generated_utc":datetime.now(timezone.utc).isoformat(),
      "database":str(db),"integrity":integrity,"rows_loaded":len(df),"eligible_rows":len(eligible),"resolved_rows":len(resolved),
      "splits":{"development":"2021-2023","calibration":"2024","holdout":"2025 (never used for rule selection)"},
      "baseline":baselines,"rules_tested":len(rules),"rules_preselected":len(selected),
      "rules_with_holdout_wilson_65":int(selected.holdout_pass_65.sum()) if len(selected) else 0,
      "rules_positive_after_0_05r_cost":int(selected.holdout_positive_after_cost.sum()) if len(selected) else 0,
      "best_rule_selected_without_holdout":best,
      "files":[f"audit_{k}.csv" for k in audits]+["all_candidate_rules.csv","top_preselected_rules_with_holdout.csv"],
      "warning":"Holdout is report-only. Do not retune thresholds using 2025 results; a new final holdout would then be required."}
    report["ambiguity_policy"]="Same-minute ambiguous outcomes are included in n and counted as non-wins."
    rp=out/"v5_point_in_time_calibration_report.json";rp.write_text(json.dumps(report,indent=2,default=str),encoding="utf-8")
    print("Phase 3/3 complete: holdout reported and compact result files written",flush=True)
    print("Trading Pulse V5 Point-in-Time Chronological Calibration")
    print(f"Rows loaded: {len(df):,} | eligible resolved: {len(resolved):,}")
    for p,m in baselines.items():print(f"{p}: n={m['n']:,} 3R={m['rate']:.4%} Wilson={m['wilson_lower']:.4%} Exp@0.05R={m['expectancy_after_0_05r_cost']:+.3f}R")
    print(f"Rules tested: {len(rules):,} | preselected: {len(selected):,}")
    print(f"65% holdout Wilson passes: {report['rules_with_holdout_wilson_65']}")
    print(f"REPORT READY: {rp}");print(f"INTEGRITY: {integrity}")


if __name__=="__main__":main()
