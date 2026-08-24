from __future__ import annotations
import argparse,json,math,sqlite3
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd

def wilson(w,n,z=1.959963984540054):
    if not n:return None
    p=w/n;d=1+z*z/n;return (p+z*z/(2*n)-z*math.sqrt((p*(1-p)+z*z/(4*n))/n))/d
def metric(g,rr=5,cost=.05):
    win=g.max_verified_r.ge(rr);amb=(~win)&g.max_possible_r.ge(rr);loss=(~win)&(~amb)&g.terminal.eq("stopped")
    w=int(win.sum());a=int(amb.sum());l=int(loss.sum());n=w+a+l;p=w/n if n else None;lo=wilson(w,n)
    return {"n":n,"wins":w,"losses":l,"ambiguous":a,"rate":p,"wilson_lower":lo,
      "expectancy_after_cost":((rr+1)*p-1-cost) if p is not None else None,
      "wilson_expectancy_after_cost":((rr+1)*lo-1-cost) if lo is not None else None}
def grouped(df,cols,rr=5):
    rows=[]
    for keys,g in df.groupby(cols,dropna=False,observed=True):
        keys=keys if isinstance(keys,tuple) else (keys,);r={c:v for c,v in zip(cols,keys)};r.update(metric(g,rr));rows.append(r)
    return pd.DataFrame(rows)
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--root",default=".");a=ap.parse_args();root=Path(a.root).resolve();db=root/"research_data/v6/professional_zone_reference.db";out=root/"research_data/v6/deep_audit";out.mkdir(parents=True,exist_ok=True)
    if not db.exists():raise SystemExit(f"V6 reference database missing: {db}")
    con=sqlite3.connect(db);integrity=con.execute("PRAGMA integrity_check").fetchone()[0];df=pd.read_sql_query("SELECT * FROM professional_zones",con);con.close()
    df.entry_ts=pd.to_datetime(df.entry_ts,utc=True);df["year"]=df.entry_ts.dt.year;df["period"]=np.where(df.year<=2023,"development",np.where(df.year==2024,"calibration",np.where(df.year==2025,"holdout","outside")))
    et=df.entry_ts.dt.tz_convert("America/New_York");df["hour_et"]=et.dt.hour;df["weekday"]=et.dt.dayofweek
    df["session"]=pd.cut(df.hour_et,[-1,2,7,12,16,23],labels=["overnight","europe","new_york_am","new_york_pm","evening"])
    elite=df[(df.ota_score>=9.5)&df.terminal.ne("not_entered")&df.period.ne("outside")].copy()
    audits={"symbol":grouped(elite,["period","symbol"]),"pattern":grouped(elite,["period","pattern"]),"direction":grouped(elite,["period","direction"]),
      "session":grouped(elite,["period","session"]),"weekday":grouped(elite,["period","weekday"]),"base_candles":grouped(elite,["period","base_candles"]),
      "year":grouped(elite,["year"]),"components":grouped(df[df.period.ne("outside")],["period","strength_score","time_score","trend_score","curve_score","profit_score"])}
    for name,x in audits.items():x.to_csv(out/f"v6_5r_by_{name}.csv",index=False)
    # Pre-holdout group selection: group must be positive in both development and calibration with adequate samples.
    selections=[]
    for dimension in ("symbol","pattern","direction","session","base_candles"):
        tab=audits[dimension];key=dimension
        for value,g in tab.groupby(key,dropna=False):
            z=g.set_index("period")
            if all(p in z.index for p in ("development","calibration","holdout")) and z.loc["development","n"]>=100 and z.loc["calibration","n"]>=30:
                pre=min(z.loc["development","expectancy_after_cost"],z.loc["calibration","expectancy_after_cost"])
                if pre>0:selections.append({"dimension":dimension,"value":str(value),"preholdout_min_expectancy":pre,
                  "development_n":int(z.loc["development","n"]),"calibration_n":int(z.loc["calibration","n"]),"holdout_n":int(z.loc["holdout","n"]),
                  "holdout_rate":z.loc["holdout","rate"],"holdout_expectancy":z.loc["holdout","expectancy_after_cost"],"holdout_wilson_expectancy":z.loc["holdout","wilson_expectancy_after_cost"]})
    selected=pd.DataFrame(selections);selected.to_csv(out/"v6_preholdout_selected_groups.csv",index=False)
    # Leave-one-symbol-out proves whether aggregate edge depends on one contract.
    loo=[]
    for sym in sorted(elite.symbol.unique()):
        for period,g in elite[elite.symbol.ne(sym)].groupby("period"):
            r={"excluded_symbol":sym,"period":period};r.update(metric(g));loo.append(r)
    pd.DataFrame(loo).to_csv(out/"v6_leave_one_symbol_out.csv",index=False)
    # Cost sensitivity at selected 9.5/5R policy.
    costs=[]
    for cost in (0,.02,.05,.075,.10,.15,.20):
        for period,g in elite.groupby("period"):
            r={"cost_r":cost,"period":period};r.update(metric(g,cost=cost));costs.append(r)
    pd.DataFrame(costs).to_csv(out/"v6_cost_sensitivity.csv",index=False)
    # Full score threshold x R matrix restricted to major subgroups for next research selection.
    matrix=[]
    for score in (8,9,9.5):
      s=df[(df.ota_score>=score)&df.terminal.ne("not_entered")&df.period.ne("outside")]
      for rr in range(1,21):
       for cols in (["period","symbol"],["period","pattern"],["period","direction"],["period","session"]):
        z=grouped(s,cols,rr);z["score_min"]=score;z["rr"]=rr;z["dimension"]="+".join(cols[1:]);matrix.append(z)
    pd.concat(matrix,ignore_index=True).to_csv(out/"v6_subgroup_rr_matrix.csv",index=False)
    overall={p:metric(g) for p,g in elite.groupby("period")};survivors=[] if selected.empty else selected[selected.holdout_expectancy>0].to_dict("records")
    report={"schema":"TP_V6_PROFESSIONAL_DEEP_AUDIT_1","generated_utc":datetime.now(timezone.utc).isoformat(),"database_integrity":integrity,"elite_policy":"OTA score >=9.5, static 5R, ambiguity as non-win","elite_rows":len(elite),"overall":overall,
      "preholdout_selected_groups":len(selected),"selected_groups_positive_in_holdout":len(survivors),"positive_holdout_groups":survivors,
      "decision":"Do not deploy unless stability, cost sensitivity, and subgroup concentration remain acceptable."}
    rp=out/"v6_deep_audit_report.json";rp.write_text(json.dumps(report,indent=2,default=str),encoding="utf-8")
    print("Trading Pulse V6 Professional Deep Audit",flush=True)
    for p,m in overall.items():print(f"{p}: n={m['n']:,} rate={m['rate']:.4%} exp={m['expectancy_after_cost']:+.4f}R Wilson-exp={m['wilson_expectancy_after_cost']:+.4f}R",flush=True)
    print(f"Pre-holdout selected groups: {len(selected)} | positive in holdout: {len(survivors)}",flush=True);print(f"REPORT READY: {rp}",flush=True);print(f"INTEGRITY: {integrity}",flush=True)
if __name__=="__main__":main()

