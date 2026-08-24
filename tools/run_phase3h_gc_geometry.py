"""GC one-minute entry/stop geometry replay under nominal 50K risk policies."""
from __future__ import annotations
import json, math, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist
import numpy as np
import pandas as pd

from core.account_risk_engine import AccountProfile, size_trade

ROOT=Path(__file__).resolve().parents[1]; SYMBOL="GC"; TICK=.1; MAX_R=5
DB=ROOT/"research_data/v6/professional_zone_reference.db"
WH=ROOT/"research_data/v5/databento_v5_warehouse.db"
RAW=ROOT/"research_data/v4/historical_blind/raw"
OUT=ROOT/"research_data/v6/canonical_phase3h"
RISK_PCTS=(1.,2.,3.); ENTRY_OFFSETS=(0.,.25,.5)

def normalize(path):
    x=pd.read_parquet(path);low={str(c).lower():c for c in x.columns}
    if "ts_event" in low:x=x.set_index(low["ts_event"])
    elif not isinstance(x.index,pd.DatetimeIndex):
        c=next((low[k] for k in ("timestamp","datetime","time","date") if k in low),None)
        if c is None:raise ValueError(f"No timestamp in {path}")
        x=x.set_index(c)
    x.index=pd.to_datetime(x.index,utc=True);low={str(c).lower():c for c in x.columns}
    x=x[[low[k] for k in ("high","low")]];x.columns=["high","low"]
    return x.sort_index()[~x.index.duplicated(keep="last")]

def load_raw():
    files=sorted(RAW.glob(f"*/{SYMBOL}__1m.parquet"))
    if len(files)!=60:raise SystemExit(f"Expected 60 GC one-minute files; found {len(files)}")
    parts=[]
    for n,p in enumerate(files,1):
        parts.append(normalize(p))
        if n%12==0:print(f"GC raw: loaded {n}/60 months",flush=True)
    x=pd.concat(parts).sort_index();return x[~x.index.duplicated(keep="last")]

def load_atr():
    con=sqlite3.connect(WH)
    x=pd.read_sql_query("SELECT timestamp,high,low,close FROM candles WHERE symbol='GC' AND timeframe='5m' AND provider='databento_v5' ORDER BY timestamp",con);con.close()
    x.timestamp=pd.to_datetime(x.timestamp,utc=True);x=x.set_index("timestamp")
    pc=x.close.shift();tr=pd.concat([x.high-x.low,(x.high-pc).abs(),(x.low-pc).abs()],axis=1).max(axis=1)
    atr=tr.rolling(14,min_periods=14).mean();atr.index=atr.index+pd.Timedelta("5min");return atr.dropna()

def purge(z,minutes=240):
    kept=[];gap=pd.Timedelta(minutes=minutes);cluster=[];start=None
    for idx,r in z.sort_values(["entry_ts","ota_score"],ascending=[True,False]).iterrows():
        if start is None or r.entry_ts-start<gap:
            cluster.append((idx,r.ota_score,r.profit_room_r));start=r.entry_ts if start is None else start
        else:
            kept.append(max(cluster,key=lambda q:(q[1],q[2]))[0]);cluster=[(idx,r.ota_score,r.profit_room_r)];start=r.entry_ts
    if cluster:kept.append(max(cluster,key=lambda q:(q[1],q[2]))[0])
    return z.loc[sorted(kept)].copy()

def configurations():
    styles=[("ORIGINAL",None),("BUFFER_TICKS",2),("BUFFER_TICKS",5),("BUFFER_TICKS",10),
            ("MIN_RISK_TICKS",20),("MIN_RISK_TICKS",30),("MIN_RISK_TICKS",40),("MIN_RISK_TICKS",50),
            ("ATR_MULT",.25),("ATR_MULT",.5),("ATR_MULT",.75),("ATR_MULT",1.)]
    return [{"config_id":f"E{int(off*100):02d}_{kind}_{value}","entry_offset":off,"stop_style":kind,"stop_value":value}
            for off in ENTRY_OFFSETS for kind,value in styles]

def prior(series,ts):
    i=series.index.searchsorted(ts,side="right")-1
    return float(series.iloc[i]) if i>=0 else None

def geometry(r,c,atr):
    width=abs(float(r.proximal)-float(r.distal));direction=r.direction
    entry=float(r.proximal)-c["entry_offset"]*width if direction=="LONG" else float(r.proximal)+c["entry_offset"]*width
    base_stop=float(r.distal)-TICK if direction=="LONG" else float(r.distal)+TICK
    base_risk=abs(entry-base_stop);style,val=c["stop_style"],c["stop_value"]
    if style=="BUFFER_TICKS":risk=base_risk+float(val)*TICK
    elif style=="MIN_RISK_TICKS":risk=max(base_risk,float(val)*TICK)
    elif style=="ATR_MULT":
        a=prior(atr,r.entry_ts);risk=max(base_risk,(a or 0)*float(val))
    else:risk=base_risk
    stop=entry-risk if direction=="LONG" else entry+risk
    return entry,stop,risk,risk/TICK

def replay(idx,hi,lo,start_ts,direction,entry,stop,risk,max_wait=120,max_minutes=14400):
    begin=idx.searchsorted(start_ts,side="left");limit=min(len(idx),begin+max_wait);entered=None
    for j in range(begin,limit):
        if lo[j]<=entry<=hi[j]:entered=j;break
    if entered is None:return None,"not_filled",0,0
    verified=possible=0;terminal="open"
    for j in range(entered,min(len(idx),entered+max_minutes)):
        fav=(hi[j]-entry)/risk if direction=="LONG" else (entry-lo[j])/risk
        reached=max(0,min(MAX_R,int(math.floor(fav+1e-10))))
        stophit=lo[j]<=stop if direction=="LONG" else hi[j]>=stop
        if j==entered:
            possible=max(possible,reached)
            if stophit:terminal="stopped";break
            continue
        if stophit:possible=max(possible,reached);terminal="stopped";break
        verified=max(verified,reached);possible=max(possible,verified)
        if verified>=MAX_R:terminal="5r_verified";break
    return idx[entered],terminal,verified,possible

def wilson(w,n,z):
    if not n:return 0.
    p=w/n;d=1+z*z/n
    return max(0.,(p+z*z/(2*n)-z*math.sqrt((p*(1-p)+z*z/(4*n))/n))/d)

def metric(g,rr,z=1.96):
    win=g.max_verified_r.ge(rr);amb=(~win)&g.max_possible_r.ge(rr);loss=(~win)&(~amb)&g.terminal.eq("stopped")
    use=win|amb|loss;n=int(use.sum());w=int(win.sum());rate=w/n if n else 0
    cost=float(g.loc[use,"cost_r"].mean()) if n else 0;lo=wilson(w,n,z)
    return {"n":n,"wins":w,"ambiguous":int(amb.sum()),"win_rate":rate,"gross_expectancy_r":(rr+1)*rate-1,
            "average_cost_r":cost,"net_expectancy_r":(rr+1)*rate-1-cost,"wilson_net_expectancy_r":(rr+1)*lo-1-cost}

def main():
    stamp=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S");out=OUT/stamp;out.mkdir(parents=True,exist_ok=True)
    for p in (DB,WH):
        if not p.exists():raise SystemExit(f"Missing canonical input: {p}")
    con=sqlite3.connect(DB);integrity=con.execute("PRAGMA integrity_check").fetchone()[0]
    z=pd.read_sql_query("SELECT * FROM professional_zones WHERE symbol='GC' AND terminal!='not_entered'",con);con.close()
    z.entry_ts=pd.to_datetime(z.entry_ts,utc=True);z=z[z.entry_ts.dt.year.between(2021,2025)].copy();z=purge(z)
    print(f"GC overlap-purged zones: {len(z):,}",flush=True)
    raw=load_raw();atr=load_atr();idx=raw.index;hi=raw.high.to_numpy(float);lo=raw.low.to_numpy(float)
    outcomes=[];configs=configurations()
    for ci,c in enumerate(configs,1):
        print(f"{ci}/{len(configs)} {c['config_id']}",flush=True)
        for r in z.itertuples(index=False):
            entry,stop,risk,risk_ticks=geometry(r,c,atr)
            fill,terminal,mv,mp=replay(idx,hi,lo,r.entry_ts,r.direction,entry,stop,risk)
            outcomes.append({"zone_id":r.zone_id,"entry_ts":r.entry_ts,"year":r.entry_ts.year,"config_id":c["config_id"],
              **c,"entry":entry,"stop":stop,"risk":risk,"risk_ticks":risk_ticks,"fill_ts":fill,"terminal":terminal,
              "max_verified_r":mv,"max_possible_r":mp})
    o=pd.DataFrame(outcomes);o["period"]=np.where(o.year<=2023,"development",np.where(o.year==2024,"calibration","holdout"))
    rows=[];case_count=len(configs)*len(RISK_PCTS)*MAX_R;adjusted_z=NormalDist().inv_cdf(1-.05/case_count)
    for pct in RISK_PCTS:
      profile=AccountProfile(risk_basis="nominal",risk_percent=pct,daily_loss_remaining=None)
      sized=[]
      for r in o.itertuples(index=False):
        d=size_trade(SYMBOL,r.risk_ticks,profile)
        sized.append((r.zone_id,r.config_id,d["eligible"],d["contract"],d["contract_type"],d["quantity"],
                      d["execution_cost_each"]/(d["structural_risk_each"] or 1)))
      sd=pd.DataFrame(sized,columns=["zone_id","config_id","eligible","contract","contract_type","quantity","cost_r"])
      x=o.merge(sd,on=["zone_id","config_id"]);x=x[x.eligible&x.terminal.ne("not_filled")]
      for config,gc in x.groupby("config_id"):
       for rr in range(1,MAX_R+1):
        for period,g in gc.groupby("period"):
         rows.append({"risk_percent":pct,"risk_budget":profile.risk_budget,"config_id":config,"rr":rr,"period":period,
                      "filled":len(g),"standard":int(g.contract_type.eq("standard").sum()),"micro":int(g.contract_type.eq("micro").sum()),
                      **metric(g,rr,adjusted_z)})
    results=pd.DataFrame(rows);results.to_csv(out/"gc_geometry_results.csv",index=False)
    selected=[]
    for keys,g in results.groupby(["risk_percent","config_id","rr"]):
      p=g.set_index("period")
      if all(k in p.index and p.loc[k,"n"]>=100 for k in ("development","calibration") ):
       pre=min(p.loc["development","net_expectancy_r"],p.loc["calibration","net_expectancy_r"])
       if pre>0:
        selected.append({"risk_percent":keys[0],"config_id":keys[1],"rr":keys[2],"preholdout_min_net_r":pre,
          **{f"{period}_{col}":p.loc[period,col] for period in p.index for col in ("n","win_rate","net_expectancy_r","wilson_net_expectancy_r")}})
    sel=pd.DataFrame(selected);sel.to_csv(out/"gc_prehholdout_selected_geometry.csv",index=False)
    # Keep detailed outcomes only for pre-holdout-selected geometry to control result size.
    chosen=set(sel.config_id) if len(sel) else set()
    o[o.config_id.isin(chosen)].to_csv(out/"gc_selected_geometry_outcomes.csv",index=False)
    positive_holdout=int((sel.get("holdout_net_expectancy_r",pd.Series(dtype=float))>0).sum()) if len(sel) else 0
    report={"schema":"TP_CANONICAL_PHASE3H_GC_GEOMETRY_1","created_utc":datetime.now(timezone.utc).isoformat(),
      "reference_integrity":integrity,"symbol":"GC","overlap_purged_zones":len(z),"configurations":len(configs),
      "entry_offsets":list(ENTRY_OFFSETS),"fill_wait_minutes":120,"outcome_horizon_minutes":14400,
      "risk_budgets":{"1%":500,"2%":1000,"3%":1500},"targets":list(range(1,6)),
      "selection":"positive net expectancy in both 2021-2023 and 2024; 2025 report-only",
      "multiple_test_cases":case_count,"adjusted_z":adjusted_z,"preholdout_selected":len(sel),
      "selected_positive_in_holdout":positive_holdout,"live_promotion":False,"integrity":"ok"}
    (out/"phase3h_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(f"OUTPUT READY: {out}");print(f"PRE-HOLDOUT SELECTED: {len(sel)}");print(f"POSITIVE IN 2025: {positive_holdout}");print("LIVE PROMOTION: False")

if __name__=="__main__":main()
