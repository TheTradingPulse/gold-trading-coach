"""Pre-registered 2026 confirmation of GC original-entry/ATR1/5R."""
from __future__ import annotations
import argparse,hashlib,json,math,os
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd

from core.account_risk_engine import AccountProfile,size_trade
from core.canonical_professional_zone_detector import detect_professional_zones

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/"research_data/v4/historical_blind/raw"
FORWARD=ROOT/"research_data/v7/forward_2026"
OUT=ROOT/"research_data/v7/phase3i_confirmation"
FROZEN=ROOT/"config/phase3i_frozen_hypothesis.json"
START="2026-01-01T00:00:00Z";END="2026-08-23T19:00:00Z";TICK=.1;RR=5

def frozen_digest():return hashlib.sha256(FROZEN.read_bytes()).hexdigest()
def data_path():return FORWARD/"GC_v_0_ohlcv_1m_20260101_20260823_1900Z.parquet"

def client():
    try:import databento as db
    except ImportError:raise SystemExit("databento package missing from .venv")
    return db.Historical(os.environ.get("DATABENTO_API_KEY"))

def quote():
    c=client();return float(c.metadata.get_cost(dataset="GLBX.MDP3",schema="ohlcv-1m",symbols="GC.v.0",stype_in="continuous",start=START,end=END))

def ensure_data(approve=False):
    p=data_path();p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():
        print(f"FORWARD DATA FOUND: {p}");return True
    cost=quote();q={"dataset":"GLBX.MDP3","schema":"ohlcv-1m","symbol":"GC.v.0","stype_in":"continuous","stype_out":"instrument_id","start":START,"end":END,"quoted_cost_usd":cost,"downloaded":False}
    (p.parent/"GC_2026_download_quote.json").write_text(json.dumps(q,indent=2),encoding="utf-8")
    print(f"DATABENTO QUOTED COST: ${cost:.4f}")
    if not approve:
        print("DOWNLOAD APPROVAL REQUIRED: rerun PowerShell with -ApproveDownload");return False
    # GLBX.MDP3 accepts continuous symbology as input, but continuous is not a
    # supported output symbology. The replay only needs timestamps and OHLCV,
    # so instrument_id is the correct lossless output representation.
    data=client().timeseries.get_range(dataset="GLBX.MDP3",schema="ohlcv-1m",symbols="GC.v.0",stype_in="continuous",stype_out="instrument_id",start=START,end=END)
    x=data.to_df();x.to_parquet(p);q["downloaded"]=True;q["rows"]=len(x);q["completed_utc"]=datetime.now(timezone.utc).isoformat()
    (p.parent/"GC_2026_download_quote.json").write_text(json.dumps(q,indent=2),encoding="utf-8")
    print(f"FORWARD DATA READY: {p} ({len(x):,} rows)");return True

def normalize(path):
    x=pd.read_parquet(path);low={str(c).lower():c for c in x.columns}
    if "ts_event" in low:x=x.set_index(low["ts_event"])
    elif not isinstance(x.index,pd.DatetimeIndex):
        c=next((low[k] for k in ("timestamp","datetime","time","date") if k in low),None)
        if c is None:raise ValueError(f"No timestamp in {path}")
        x=x.set_index(c)
    x.index=pd.to_datetime(x.index,utc=True);low={str(c).lower():c for c in x.columns}
    keep=[k for k in ("open","high","low","close","volume") if k in low];x=x[[low[k] for k in keep]];x.columns=keep
    if "volume" not in x:x["volume"]=0
    return x.sort_index()[~x.index.duplicated(keep="last")]

def load_combined():
    history=[]
    for month in ("2025-10","2025-11","2025-12"):
        p=RAW/month/"GC__1m.parquet"
        if not p.exists():raise SystemExit(f"Warmup file missing: {p}")
        history.append(normalize(p))
    history.append(normalize(data_path()));x=pd.concat(history).sort_index();return x[~x.index.duplicated(keep="last")]

def bars(x,rule):
    return x.resample(rule,label="left",closed="left").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna(subset=["open","high","low","close"])

def atr14(m5):
    pc=m5.close.shift();tr=pd.concat([m5.high-m5.low,(m5.high-pc).abs(),(m5.low-pc).abs()],axis=1).max(axis=1)
    a=tr.rolling(14,min_periods=14).mean();a.index=a.index+pd.Timedelta("5min");return a.dropna()

def prior(s,ts):
    i=s.index.searchsorted(ts,side="right")-1;return float(s.iloc[i]) if i>=0 else None

def purge(z):
    kept=[];cluster=[];start=None;gap=pd.Timedelta("240min")
    for idx,r in z.sort_values(["entry_ts","ota_score"],ascending=[True,False]).iterrows():
        if start is None or r.entry_ts-start<gap:
            cluster.append((idx,r.ota_score,r.profit_room_r));start=r.entry_ts if start is None else start
        else:
            kept.append(max(cluster,key=lambda q:(q[1],q[2]))[0]);cluster=[(idx,r.ota_score,r.profit_room_r)];start=r.entry_ts
    if cluster:kept.append(max(cluster,key=lambda q:(q[1],q[2]))[0])
    return z.loc[sorted(kept)].copy()

def replay(idx,hi,lo,start,direction,entry,stop,risk):
    begin=idx.searchsorted(start,side="left");entered=None
    for j in range(begin,min(len(idx),begin+120)):
        if lo[j]<=entry<=hi[j]:entered=j;break
    if entered is None:return None,"not_filled",0,0
    verified=possible=0;terminal="open"
    for j in range(entered,min(len(idx),entered+14400)):
        fav=(hi[j]-entry)/risk if direction=="LONG" else (entry-lo[j])/risk;reached=max(0,min(RR,int(math.floor(fav+1e-10))))
        stophit=lo[j]<=stop if direction=="LONG" else hi[j]>=stop
        if j==entered:
            possible=max(possible,reached)
            if stophit:terminal="stopped";break
            continue
        if stophit:possible=max(possible,reached);terminal="stopped";break
        verified=max(verified,reached);possible=max(possible,verified)
        if verified>=RR:terminal="5r_verified";break
    return idx[entered],terminal,verified,possible

def streak(values):
    best=cur=0
    for v in values:
        cur=cur+1 if v<0 else 0;best=max(best,cur)
    return best

def main(approve=False):
    if not ensure_data(approve):return 3
    stamp=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S");out=OUT/stamp;out.mkdir(parents=True,exist_ok=True)
    raw=load_combined();m5=bars(raw,"5min");m15=bars(raw,"15min");h1=bars(raw,"1h");a=atr14(m5)
    zones=detect_professional_zones("GC",m5,m15,h1);zones.entry_ts=pd.to_datetime(zones.entry_ts,utc=True)
    zones=purge(zones[(zones.entry_ts>=pd.Timestamp(START))&(zones.entry_ts<pd.Timestamp(END))])
    idx=raw.index;hi=raw.high.to_numpy(float);lo=raw.low.to_numpy(float);outcomes=[]
    for r in zones.itertuples(index=False):
        entry=float(r.entry);base=abs(float(r.entry)-float(r.stop));risk=max(base,prior(a,r.entry_ts) or 0);stop=entry-risk if r.direction=="LONG" else entry+risk
        fill,terminal,mv,mp=replay(idx,hi,lo,r.entry_ts,r.direction,entry,stop,risk)
        outcomes.append({"zone_id":r.zone_id,"entry_ts":r.entry_ts,"fill_ts":fill,"pattern":r.pattern,"direction":r.direction,
          "ota_score":r.ota_score,"entry":entry,"stop":stop,"risk":risk,"risk_ticks":risk/TICK,"terminal":terminal,"max_verified_r":mv,"max_possible_r":mp})
    o=pd.DataFrame(outcomes);o["month"]=pd.to_datetime(o.entry_ts,utc=True).dt.to_period("M").astype(str)
    et=pd.to_datetime(o.entry_ts,utc=True).dt.tz_convert("America/New_York");o["hour_et"]=et.dt.hour
    o["session"]=pd.cut(o.hour_et,[-1,2,7,12,16,23],labels=["overnight","europe","new_york_am","new_york_pm","evening"])
    summaries=[];detail=[]
    for pct in (1.,2.,3.):
        profile=AccountProfile(risk_basis="nominal",risk_percent=pct,daily_loss_remaining=None)
        for r in o.itertuples(index=False):
            d=size_trade("GC",r.risk_ticks,profile);cost_r=d["execution_cost_each"]/(d["structural_risk_each"] or 1)
            win=r.max_verified_r>=RR;amb=(not win) and r.max_possible_r>=RR;eligible=d["eligible"] and r.terminal not in ("not_filled","open")
            result_r=(RR-cost_r if win else -1-cost_r) if eligible else np.nan
            detail.append({**r._asdict(),"risk_percent":pct,"risk_budget":profile.risk_budget,"eligible":eligible,"contract":d["contract"],"quantity":d["quantity"],"ambiguous":amb,"result_r":result_r,"result_usd":result_r*d["structural_risk_each"]*d["quantity"] if eligible else np.nan})
    d=pd.DataFrame(detail);d.to_csv(out/"phase3i_trade_details.csv",index=False)
    for pct,g in d[d.eligible].groupby("risk_percent"):
        resolved=g[g.result_r.notna()];wins=int((resolved.result_r>0).sum());n=len(resolved);rate=wins/n if n else 0
        equity=resolved.sort_values("entry_ts").result_usd.cumsum();dd=equity-equity.cummax();daily=resolved.assign(day=pd.to_datetime(resolved.entry_ts,utc=True).dt.date).groupby("day").result_usd.sum()
        summaries.append({"risk_percent":pct,"risk_budget":float(g.risk_budget.iloc[0]),"n":n,"wins":wins,"win_rate":rate,
          "average_r":float(resolved.result_r.mean()),"total_usd":float(resolved.result_usd.sum()),"max_closed_trade_drawdown_usd":float(dd.min()),
          "max_losing_streak":streak(resolved.sort_values("entry_ts").result_r),"worst_day_usd":float(daily.min()),
          "initial_2000_drawdown_breached":bool(dd.min()<=-2000),"eod_1000_dll_breached":bool(daily.min()<=-1000)})
    pd.DataFrame(summaries).to_csv(out/"phase3i_account_results.csv",index=False)
    breakdown=[]
    for dims in (("direction",),("pattern",),("session",),("month",)):
      for keys,g in d[(d.risk_percent==1)&d.eligible].groupby(list(dims),observed=True):
        keys=keys if isinstance(keys,tuple) else (keys,);breakdown.append({"dimension":"+".join(dims),"value":"+".join(map(str,keys)),"n":len(g),"win_rate":float((g.result_r>0).mean()),"average_r":float(g.result_r.mean())})
    pd.DataFrame(breakdown).to_csv(out/"phase3i_stability_breakdown.csv",index=False)
    report={"schema":"TP_PHASE3I_FROZEN_CONFIRMATION_1","created_utc":datetime.now(timezone.utc).isoformat(),"frozen_hypothesis_sha256":frozen_digest(),
      "confirmation_period":{"start":START,"end_exclusive":END},"zones_detected":len(zones),"data_rows":len(raw),"parameter_search":False,
      "account_results":summaries,"live_promotion":False,"integrity":"ok"}
    (out/"phase3i_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(f"OUTPUT READY: {out}");print(f"FORWARD ZONES: {len(zones)}");print("PARAMETER SEARCH: False");print("LIVE PROMOTION: False");return 0

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--approve-download",action="store_true");args=ap.parse_args();raise SystemExit(main(args.approve_download))
