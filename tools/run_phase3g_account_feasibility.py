"""Five-year Apex 50K standard/micro feasibility lab."""
from __future__ import annotations
import json, math, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist
import numpy as np
import pandas as pd

from core.account_risk_engine import AccountProfile, size_trade

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/"research_data/v6/professional_zone_reference.db"
OUT=ROOT/"research_data/v6/canonical_phase3g"
POLICIES=(1.0,2.0,3.0); RRS=range(1,6)
SEEDS=(
 ("ALL",None,None),("GC", "symbol","GC"),("OTA7","ota_score__gte",7.0),
 ("OTA8","ota_score__gte",8.0),("BASE1","base_candles",1),
 ("RBD","pattern","RBD"),("LONG","direction","LONG"),
 ("DEPARTURE","departure_ratio__gte",2.636360483738761),
)

def apply_seed(df,feature,value):
    if feature is None:return df
    if feature.endswith("__gte"):return df[pd.to_numeric(df[feature[:-5]],errors="coerce")>=float(value)]
    return df[df[feature].astype(str)==str(value)]

def wilson(w,n,z=1.96):
    if not n:return 0.
    p=w/n;d=1+z*z/n
    return max(0.,(p+z*z/(2*n)-z*math.sqrt((p*(1-p)+z*z/(4*n))/n))/d)

def metric(g,rr):
    win=g.max_verified_r.ge(rr);amb=(~win)&g.max_possible_r.ge(rr);loss=(~win)&(~amb)&g.terminal.eq("stopped")
    use=win|amb|loss;n=int(use.sum());w=int(win.sum());rate=w/n if n else 0
    avg_cost=float(g.loc[use,"selected_cost_r"].mean()) if n else 0
    lo=wilson(w,n)
    return {"n":n,"wins":w,"ambiguous":int(amb.sum()),"win_rate":rate,"wilson_lower":lo,
      "gross_expectancy_r":(rr+1)*rate-1,"average_cost_r":avg_cost,
      "net_expectancy_r":(rr+1)*rate-1-avg_cost,"wilson_net_expectancy_r":(rr+1)*lo-1-avg_cost}

def main():
    stamp=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S");out=OUT/stamp;out.mkdir(parents=True,exist_ok=True)
    if not DB.exists():raise SystemExit(f"V6 reference missing: {DB}")
    con=sqlite3.connect(DB);integrity=con.execute("PRAGMA integrity_check").fetchone()[0]
    z=pd.read_sql_query("SELECT * FROM professional_zones",con);con.close()
    z.entry_ts=pd.to_datetime(z.entry_ts,utc=True);z["year"]=z.entry_ts.dt.year
    z=z[z.year.between(2021,2025)&z.terminal.ne("not_entered")].copy()
    z["period"]=np.where(z.year<=2023,"development",np.where(z.year==2024,"calibration","holdout"))
    rows=[];decisions=[]
    for pct in POLICIES:
      profile=AccountProfile(risk_basis="nominal",risk_percent=pct,daily_loss_remaining=None)
      print(f"Apex 50K nominal-balance policy: {pct:.0f}% = ${profile.risk_budget:.2f}",flush=True)
      ds=[]
      for r in z.itertuples(index=False):
        d=size_trade(r.symbol,float(r.risk_ticks),profile)
        selected_cost_r=(d["execution_cost_each"]/(d["structural_risk_each"] or 1)) if d["eligible"] else np.nan
        ds.append((r.zone_id,d["eligible"],d["status"],d["contract"],d["contract_type"],d["quantity"],
                   d["risk_budget"],d["total_risk_each"],d["total_position_risk"],d["execution_cost_percent"],selected_cost_r,
                   d["minimum_bankroll_1pct"],d["minimum_bankroll_2pct"],d["minimum_bankroll_3pct"]))
      dd=pd.DataFrame(ds,columns=["zone_id","eligible","status","contract","contract_type","quantity","risk_budget",
          "total_risk_each","total_position_risk","execution_cost_percent","selected_cost_r",
          "minimum_bankroll_1pct","minimum_bankroll_2pct","minimum_bankroll_3pct"])
      x=z.merge(dd,on="zone_id",how="left");x["risk_percent"]=pct;decisions.append(x)
      print(f"  executable={int(x.eligible.sum()):,}/{len(x):,} ({x.eligible.mean():.2%})",flush=True)
      e=x[x.eligible].copy()
      for seed,feature,value in SEEDS:
       s=apply_seed(e,feature,value)
       for rr in RRS:
        for period,g in s.groupby("period"):
         rows.append({"risk_percent":pct,"risk_budget":profile.risk_budget,"seed":seed,"feature":feature,"value":value,
                      "rr":rr,"period":period,**metric(g,rr),"standard":int(g.contract_type.eq("standard").sum()),
                      "micro":int(g.contract_type.eq("micro").sum())})
    all_decisions=pd.concat(decisions,ignore_index=True);results=pd.DataFrame(rows)
    decision_columns=["zone_id","symbol","entry_ts","year","period","risk_ticks","risk_percent","status","contract",
      "contract_type","quantity","risk_budget","total_risk_each","total_position_risk","execution_cost_percent",
      "minimum_bankroll_1pct","minimum_bankroll_2pct","minimum_bankroll_3pct"]
    all_decisions.loc[all_decisions.eligible,decision_columns].to_csv(out/"account_feasibility_eligible_trades.csv",index=False)
    all_decisions.groupby(["risk_percent","symbol","status"],dropna=False).size().rename("trades").reset_index().to_csv(out/"account_feasibility_status_summary.csv",index=False)
    results.to_csv(out/"account_policy_rr_results.csv",index=False)
    viable=[]
    for keys,g in results.groupby(["risk_percent","seed","rr"]):
      p=g.set_index("period")
      if all(k in p.index and p.loc[k,"n"]>=150 for k in ("development","calibration","holdout")):
        if all(p.loc[k,"net_expectancy_r"]>0 for k in ("development","calibration","holdout")):
          viable.append({"risk_percent":keys[0],"seed":keys[1],"rr":keys[2],
                         **{f"{period}_{col}":p.loc[period,col] for period in p.index for col in ("n","win_rate","net_expectancy_r","wilson_net_expectancy_r")}})
    pd.DataFrame(viable).to_csv(out/"account_aware_viable_policies.csv",index=False)
    report={"schema":"TP_CANONICAL_PHASE3G_ACCOUNT_FEASIBILITY_2","created_utc":datetime.now(timezone.utc).isoformat(),
      "reference_integrity":integrity,"reference_rows":len(z),"account":"Apex 50K EOD PA Level 1",
      "effective_drawdown":2000,"daily_loss_limit":1000,"max_standard_equivalents":2,
      "risk_basis":"nominal advertised balance","risk_policies":{"1%":500,"2%":1000,"3%":1500},
      "apex_compliance_warnings":{"1%":"Consumes 25% of initial $2,000 drawdown capacity if fully lost.",
        "2%":"Equals the current $1,000 EOD daily loss limit and 50% of initial drawdown capacity.",
        "3%":"Exceeds the current $1,000 EOD daily loss limit and consumes 75% of initial drawdown capacity."},
      "contract_selection":"standard if feasible, otherwise micro",
      "max_execution_cost_percent":10,"targets":[1,2,3,4,5],"viable_policies":len(viable),
      "live_promotion":False,"integrity":"ok"}
    (out/"phase3g_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(f"OUTPUT READY: {out}");print(f"VIABLE ACCOUNT-AWARE POLICIES: {len(viable)}");print("LIVE PROMOTION: False")

if __name__=="__main__":main()
