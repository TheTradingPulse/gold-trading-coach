from __future__ import annotations

import argparse, json, math, sqlite3
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

SYMBOLS=("GC","SI","ES","NQ","YM","RTY","CL","NG")
MAX_R=20

def wilson(w,n,z=1.959963984540054):
    if not n:return None
    p=w/n;d=1+z*z/n
    return (p+z*z/(2*n)-z*math.sqrt((p*(1-p)+z*z/(4*n))/n))/d

def normalize(path):
    x=pd.read_parquet(path);low={str(c).lower():c for c in x.columns}
    if "ts_event" in low:x=x.set_index(low["ts_event"])
    elif not isinstance(x.index,pd.DatetimeIndex):
        c=next((low[k] for k in ("timestamp","datetime","time","date") if k in low),None)
        if c is None:raise ValueError(f"No timestamp in {path}")
        x=x.set_index(c)
    x.index=pd.to_datetime(x.index,utc=True)
    low={str(c).lower():c for c in x.columns}
    x=x[[low[k] for k in ("high","low")]];x.columns=["high","low"]
    return x.sort_index()[~x.index.duplicated(keep="last")]

def load_raw(root,symbol):
    files=sorted((root/"research_data/v4/historical_blind/raw").glob(f"*/{symbol}__1m.parquet"))
    if len(files)!=60:raise RuntimeError(f"{symbol}: expected 60 one-minute files, found {len(files)}")
    parts=[]
    for n,p in enumerate(files,1):
        parts.append(normalize(p))
        if n%12==0:print(f"  loaded {n}/60 months",flush=True)
    x=pd.concat(parts).sort_index()
    return x[~x.index.duplicated(keep="last")]

def walk(candidates,raw,max_minutes):
    idx=raw.index;hi=raw.high.to_numpy(float);lo=raw.low.to_numpy(float);rows=[]
    for n,r in enumerate(candidates.itertuples(index=False),1):
        if pd.isna(r.entered_at):
            rows.append((r.candidate_id,r.symbol,r.detected_at,r.direction,r.trend_aligned,"not_entered",0,0))
            continue
        start=idx.searchsorted(pd.Timestamp(r.entered_at),side="left");end=min(len(idx),start+max_minutes)
        verified=0;possible=0;terminal="open"
        for j in range(start,end):
            favorable=(hi[j]-r.entry)/r.risk if r.direction=="LONG" else (r.entry-lo[j])/r.risk
            reached=max(0,min(MAX_R,int(math.floor(favorable+1e-10))))
            stop_hit=lo[j]<=r.stop if r.direction=="LONG" else hi[j]>=r.stop
            if j==start:
                # Entry and target order inside the entry minute is unknowable.
                possible=max(possible,reached)
                if stop_hit:terminal="stopped";break
                continue
            if stop_hit:
                possible=max(possible,reached);terminal="stopped";break
            verified=max(verified,reached);possible=max(possible,verified)
            if verified>=MAX_R:terminal="20r_verified";break
        rows.append((r.candidate_id,r.symbol,r.detected_at,r.direction,r.trend_aligned,terminal,verified,possible))
        if n%5000==0:print(f"  processed {n:,}/{len(candidates):,} candidates",flush=True)
    return pd.DataFrame(rows,columns=["candidate_id","symbol","detected_at","direction","trend_aligned","terminal","max_verified_r","max_possible_r"])

def ladder_rows(paths):
    x=pd.concat([pd.read_csv(p) for p in paths],ignore_index=True)
    x["detected_at"]=pd.to_datetime(x.detected_at,utc=True);x["year"]=x.detected_at.dt.year
    x["period"]=np.where(x.year<=2023,"development",np.where(x.year==2024,"calibration",np.where(x.year==2025,"holdout","outside")))
    x=x[(x.period!="outside")&(x.terminal!="not_entered")]
    rows=[]
    groups=[("ALL",x)]+[(s,g) for s,g in x.groupby("symbol")]
    for group,g in groups:
      for period,p in g.groupby("period"):
       for rr in range(1,MAX_R+1):
        win=p.max_verified_r.ge(rr)
        amb=(~win)&p.max_possible_r.ge(rr)
        loss=(~win)&(~amb)&p.terminal.eq("stopped")
        opened=(~win)&(~amb)&(~loss)
        w=int(win.sum());a=int(amb.sum());l=int(loss.sum());o=int(opened.sum());resolved=w+l
        rate=w/resolved if resolved else None;cons_n=w+l+a;cons=w/cons_n if cons_n else None
        rows.append({"group":group,"period":period,"rr":rr,"wins":w,"losses":l,"ambiguous":a,"open":o,
          "resolved_n":resolved,"verified_rate":rate,"wilson_lower":wilson(w,resolved),
          "conservative_n":cons_n,"conservative_rate":cons,
          "gross_expectancy_r":((rr+1)*rate-1) if rate is not None else None,
          "expectancy_after_0_05r_cost":((rr+1)*rate-1-.05) if rate is not None else None,
          "conservative_expectancy_after_0_05r_cost":((rr+1)*cons-1-.05) if cons is not None else None})
    return pd.DataFrame(rows)

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--root",default=".");ap.add_argument("--max-minutes",type=int,default=14400);a=ap.parse_args()
    root=Path(a.root).resolve();db=root/"research_data/v5/replay_point_in_time/databento_v5_evidence_point_in_time.db"
    out=root/"research_data/v5/rr_ladder";check=out/"checkpoints";check.mkdir(parents=True,exist_ok=True)
    if not db.exists():raise SystemExit(f"Corrected point-in-time evidence DB missing: {db}")
    con=sqlite3.connect(db);integrity=con.execute("PRAGMA integrity_check").fetchone()[0]
    q="""SELECT candidate_id,symbol,detected_at,direction,entry,stop,risk,trend_aligned,entered_at
         FROM candidates WHERE execution_eligible=1 ORDER BY symbol,detected_at"""
    candidates=pd.read_sql_query(q,con);con.close()
    print(f"Loaded {len(candidates):,} corrected eligible candidates; integrity={integrity}",flush=True)
    paths=[]
    for symbol in SYMBOLS:
        p=check/f"{symbol}_rr_path.csv";paths.append(p)
        if p.exists():print(f"\n{symbol}: checkpoint exists; skipping",flush=True);continue
        print(f"\n{symbol}: loading authoritative one-minute bars",flush=True)
        raw=load_raw(root,symbol);c=candidates[candidates.symbol.eq(symbol)].copy()
        result=walk(c,raw,a.max_minutes);result.to_csv(p,index=False)
        print(f"  CHECKPOINT READY: {p}",flush=True)
    ladder=ladder_rows(paths);lp=out/"v5_rr_1_to_20_ladder.csv";ladder.to_csv(lp,index=False)
    overall=ladder[ladder.group.eq("ALL")].copy()
    pivot=overall.pivot(index="rr",columns="period",values="conservative_expectancy_after_0_05r_cost")
    eligible=pivot.dropna().copy();eligible["selection_score"]=eligible[["development","calibration"]].min(axis=1)
    chosen_rr=int(eligible.selection_score.idxmax())
    chosen=overall[overall.rr.eq(chosen_rr)].set_index("period").to_dict("index")
    report={"schema":"TP_V5_POINT_IN_TIME_RR_LADDER_1","generated_utc":datetime.now(timezone.utc).isoformat(),
      "integrity":integrity,"candidates_loaded":len(candidates),"targets_tested":list(range(1,MAX_R+1)),
      "splits":{"development":"2021-2023","calibration":"2024","holdout":"2025 report-only"},
      "selection_method":"Highest minimum conservative expectancy across development and calibration; 2025 excluded.",
      "selected_rr_without_holdout":chosen_rr,"selected_rr_results":chosen,
      "ambiguity_policy":"Targets touched in the entry minute or in the same minute as the stop are not verified wins.",
      "cost_warning":"0.05R is provisional. Contract-specific commissions and slippage still require modeling.",
      "files":[lp.name,"v5_rr_holdout_by_symbol.csv"]}
    hp=out/"v5_rr_holdout_by_symbol.csv";ladder[(ladder.period.eq("holdout"))&(~ladder.group.eq("ALL"))].to_csv(hp,index=False)
    rp=out/"v5_rr_ladder_report.json";rp.write_text(json.dumps(report,indent=2,default=str),encoding="utf-8")
    print("\nTrading Pulse V5 Point-in-Time R:R Ladder",flush=True)
    print(f"Selected without holdout: {chosen_rr}R",flush=True)
    for period,m in chosen.items():print(f"  {period}: n={m['conservative_n']:,} rate={m['conservative_rate']:.4%} exp={m['conservative_expectancy_after_0_05r_cost']:+.4f}R",flush=True)
    print(f"REPORT READY: {rp}",flush=True);print(f"INTEGRITY: {integrity}",flush=True)

if __name__=="__main__":main()

