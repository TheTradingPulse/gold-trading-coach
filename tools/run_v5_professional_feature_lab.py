from __future__ import annotations
import argparse,json,math,sqlite3
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd

PROVIDER="databento_v5";SYMBOLS=("GC","SI","ES","NQ","YM","RTY","CL","NG")

def atr(x,n=14):
    prev=x.close.shift();tr=pd.concat([x.high-x.low,(x.high-prev).abs(),(x.low-prev).abs()],axis=1).max(axis=1)
    return tr.rolling(n,min_periods=n).mean()

def read_tf(con,symbol,tf):
    q="""SELECT timestamp,open,high,low,close,volume FROM candles
         WHERE symbol=? AND timeframe=? AND provider=? ORDER BY timestamp"""
    x=pd.read_sql_query(q,con,params=(symbol,tf,PROVIDER));x.timestamp=pd.to_datetime(x.timestamp,utc=True)
    return x.set_index("timestamp")

def common_features(x,prefix,duration):
    a=atr(x);r=(x.high-x.low).replace(0,np.nan);ma20=x.close.rolling(20,min_periods=20).mean();ma50=x.close.rolling(50,min_periods=50).mean()
    out=pd.DataFrame(index=x.index+pd.Timedelta(duration))
    out[f"{prefix}_range_atr"]=(r/a).to_numpy()
    out[f"{prefix}_body_ratio"]=((x.close-x.open).abs()/r).to_numpy()
    out[f"{prefix}_volume_ratio"]=(x.volume/x.volume.rolling(20,min_periods=20).mean().shift(1)).to_numpy()
    out[f"{prefix}_slope5_atr"]=((ma20-ma20.shift(5))/(5*a)).to_numpy()
    out[f"{prefix}_trend_strength"]=(abs(ma20-ma50)/a).to_numpy()
    hi=x.high.rolling(50,min_periods=50).max();lo=x.low.rolling(50,min_periods=50).min()
    out[f"{prefix}_range_position"]=((x.close-lo)/(hi-lo).replace(0,np.nan)).to_numpy()
    return out.reset_index(names="available_at")

def daily_features(x):
    a=atr(x);hi20=x.high.rolling(20,min_periods=20).max();lo20=x.low.rolling(20,min_periods=20).min()
    pct=a.rolling(252,min_periods=60).rank(pct=True);ma20=x.close.rolling(20,min_periods=20).mean()
    out=pd.DataFrame(index=x.index+pd.Timedelta("1D"))
    out["d_atr_regime_pct"]=pct.to_numpy();out["d_curve_position"]=((x.close-lo20)/(hi20-lo20).replace(0,np.nan)).to_numpy()
    out["d_slope5_atr"]=((ma20-ma20.shift(5))/(5*a)).to_numpy();out["d_prior_return_atr"]=((x.close-x.open)/a).to_numpy()
    return out.reset_index(names="available_at")

def asof_add(left,right,on="detected_at"):
    order=left.index
    a=left.sort_values(on);b=right.sort_values("available_at")
    z=pd.merge_asof(a,b,left_on=on,right_on="available_at",direction="backward",allow_exact_matches=True).drop(columns="available_at")
    return z.set_index(a.index).reindex(order)

def base_features(c,m15):
    x=m15.copy();a=atr(x);rng=(x.high-x.low).replace(0,np.nan);volmean=x.volume.rolling(20,min_periods=20).mean().shift(1)
    lookup=pd.DataFrame({"base_at":x.index,"base_range_atr":rng/a,"base_volume_ratio":x.volume/volmean,
      "base_close_location":(x.close-x.low)/rng,"prior50_high":x.high.rolling(50,min_periods=50).max().shift(1),
      "prior50_low":x.low.rolling(50,min_periods=50).min().shift(1)})
    z=c.merge(lookup,on="base_at",how="left")
    room=np.where(z.direction.eq("LONG"),(z.prior50_high-z.entry)/z.risk,(z.entry-z.prior50_low)/z.risk)
    z["opposing_room_r"]=np.maximum(0,room)
    # Count preceding bars that overlap the future base zone: a proxy for fresh vs repeatedly traded structure.
    idx=m15.index;hi=m15.high.to_numpy();lo=m15.low.to_numpy();counts=[]
    positions=idx.get_indexer(z.base_at)
    for pos,entry,stop in zip(positions,z.entry,z.stop):
        if pos<0:counts.append(np.nan);continue
        zone_hi=max(entry,stop);zone_lo=min(entry,stop);start=max(0,pos-40)
        counts.append(int(np.count_nonzero((hi[start:pos]>=zone_lo)&(lo[start:pos]<=zone_hi))))
    z["prior_zone_overlap_40"]=counts
    return z.drop(columns=["prior50_high","prior50_low"])

def sigmoid(v):
    v=np.clip(v,-35,35);return 1/(1+np.exp(-v))

def fit_logit(X,y,lam,steps=35):
    b=np.zeros(X.shape[1])
    penalty=np.eye(X.shape[1])*lam;penalty[0,0]=0
    for _ in range(steps):
        p=sigmoid(X@b);w=np.maximum(p*(1-p),1e-6)
        h=X.T@(X*w[:,None])+penalty;g=X.T@(y-p)-penalty@b
        step=np.linalg.solve(h,g);b+=step
        if np.max(abs(step))<1e-7:break
    return b

def logloss(y,p):
    p=np.clip(p,1e-9,1-1e-9);return float(np.mean(-(y*np.log(p)+(1-y)*np.log(1-p))))

def wilson(w,n,z=1.959963984540054):
    if not n:return None
    p=w/n;d=1+z*z/n
    return (p+z*z/(2*n)-z*math.sqrt((p*(1-p)+z*z/(4*n))/n))/d

def cohort(y,p,mask):
    yy=y[mask];n=len(yy);w=int(yy.sum());rate=w/n if n else None
    return {"n":n,"wins":w,"rate":rate,"wilson_lower":wilson(w,n),
      "expectancy_3r_after_0_05r":4*rate-1-.05 if rate is not None else None,
      "mean_model_probability":float(p[mask].mean()) if n else None}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--root",default=".");a=ap.parse_args();root=Path(a.root).resolve()
    evidence=root/"research_data/v5/replay_point_in_time/databento_v5_evidence_point_in_time.db"
    warehouse=root/"research_data/v5/databento_v5_warehouse.db";out=root/"research_data/v5/professional_feature_lab";out.mkdir(parents=True,exist_ok=True)
    if not evidence.exists() or not warehouse.exists():raise SystemExit("Corrected evidence DB or V5 warehouse missing")
    ec=sqlite3.connect(evidence);integrity_e=ec.execute("PRAGMA integrity_check").fetchone()[0]
    q="""SELECT candidate_id,symbol,detected_at,base_at,direction,entry,stop,risk,risk_ticks,risk_daily_atr,
    departure_strength,base_body_ratio,trend_aligned,execution_eligible,outcome FROM candidates WHERE execution_eligible=1"""
    c=pd.read_sql_query(q,ec);ec.close();c.detected_at=pd.to_datetime(c.detected_at,utc=True);c.base_at=pd.to_datetime(c.base_at,utc=True)
    c=c[c.outcome.isin(["target_3r_first","stop_first","same_minute_ambiguous"])].copy();c["win"]=c.outcome.eq("target_3r_first").astype(int)
    wc=sqlite3.connect(warehouse);integrity_w=wc.execute("PRAGMA integrity_check").fetchone()[0];parts=[]
    for symbol in SYMBOLS:
        print(f"\n{symbol}: engineering point-in-time professional features",flush=True)
        z=c[c.symbol.eq(symbol)].copy();m15=read_tf(wc,symbol,"15m");h1=read_tf(wc,symbol,"1H");h4=read_tf(wc,symbol,"4H");d=read_tf(wc,symbol,"D")
        z=base_features(z,m15)
        z=asof_add(z,common_features(m15,"m15","15min"));z=asof_add(z,common_features(h1,"h1","1h"));z=asof_add(z,common_features(h4,"h4","4h"));z=asof_add(z,daily_features(d))
        parts.append(z);print(f"  enriched {len(z):,} adjudicated candidates",flush=True)
    wc.close();df=pd.concat(parts,ignore_index=True);df["year"]=df.detected_at.dt.year
    et=df.detected_at.dt.tz_convert("America/New_York");df["hour_et"]=et.dt.hour;df["weekday"]=et.dt.dayofweek
    df["session"]=pd.cut(df.hour_et,[-1,2,7,12,16,23],labels=["overnight","europe","new_york_am","new_york_pm","evening"])
    df["period"]=np.where(df.year<=2023,"development",np.where(df.year==2024,"calibration",np.where(df.year==2025,"holdout","outside")))
    numeric=["risk_ticks","risk_daily_atr","departure_strength","base_body_ratio","base_range_atr","base_volume_ratio","base_close_location","opposing_room_r","prior_zone_overlap_40",
      "m15_range_atr","m15_body_ratio","m15_volume_ratio","m15_slope5_atr","m15_trend_strength","m15_range_position",
      "h1_range_atr","h1_body_ratio","h1_volume_ratio","h1_slope5_atr","h1_trend_strength","h1_range_position",
      "h4_range_atr","h4_body_ratio","h4_volume_ratio","h4_slope5_atr","h4_trend_strength","h4_range_position",
      "d_atr_regime_pct","d_curve_position","d_slope5_atr","d_prior_return_atr"]
    categorical=["symbol","direction","session","weekday"]
    dev=df.period.eq("development");cal=df.period.eq("calibration");hold=df.period.eq("holdout")
    design=[];names=["intercept"]
    for col in numeric:
        v=pd.to_numeric(df[col],errors="coerce");med=v[dev].median();v=v.fillna(med);mu=v[dev].mean();sd=v[dev].std() or 1
        design.append(((v-mu)/sd).clip(-8,8).to_numpy());names.append(col)
    for col in categorical:
        vals=df[col].astype(str);cats=sorted(vals[dev].unique())
        for cat in cats[1:]:design.append(vals.eq(cat).astype(float).to_numpy());names.append(f"{col}={cat}")
    X=np.column_stack([np.ones(len(df))]+design);y=df.win.to_numpy(float)
    print(f"\nTraining interpretable logistic model with {X.shape[1]-1} point-in-time features",flush=True)
    candidates=[]
    for lam in (.1,1.,10.,100.):
        b=fit_logit(X[dev],y[dev],lam);pc=sigmoid(X[cal]@b);candidates.append((logloss(y[cal],pc),lam,b));print(f"  L2={lam:g} calibration log loss={candidates[-1][0]:.6f}",flush=True)
    loss,lam,b=min(candidates,key=lambda t:t[0]);pred=sigmoid(X@b)
    coef=pd.DataFrame({"feature":names,"coefficient":b,"absolute_coefficient":abs(b)}).sort_values("absolute_coefficient",ascending=False);coef.to_csv(out/"feature_coefficients.csv",index=False)
    # Thresholds are fixed exclusively from 2024 score percentiles, then applied unchanged to all periods.
    rows=[]
    for pct in (50,70,80,90,95,98):
        threshold=float(np.percentile(pred[cal],pct))
        for period,pmask in (("development",dev),("calibration",cal),("holdout",hold)):
            m=pmask&(pred>=threshold);row={"calibration_percentile_threshold":pct,"score_threshold":threshold,"period":period};row.update(cohort(y,pred,m));rows.append(row)
    cohorts=pd.DataFrame(rows);cohorts.to_csv(out/"chronological_score_cohorts.csv",index=False)
    # One-dimensional feature quintiles expose stable/non-stable professional inputs.
    audits=[]
    for col in numeric:
        v=pd.to_numeric(df[col],errors="coerce");edges=np.unique(v[dev].quantile([0,.2,.4,.6,.8,1]).dropna())
        if len(edges)<3:continue
        bins=pd.cut(v,edges,include_lowest=True,duplicates="drop")
        for period,pmask in (("development",dev),("calibration",cal),("holdout",hold)):
            for band,g in df[pmask].assign(_band=bins[pmask]).groupby("_band",observed=True):
                m=g.win;audits.append({"feature":col,"period":period,"band":str(band),"n":len(g),"rate":float(m.mean()),"wins":int(m.sum())})
    pd.DataFrame(audits).to_csv(out/"feature_quintile_audit.csv",index=False)
    export_columns=list(dict.fromkeys(["candidate_id","symbol","detected_at","direction","outcome","win","period"]+numeric+categorical))
    feature_path=out/"professional_features.db";feature_con=sqlite3.connect(feature_path)
    df[export_columns].to_sql("professional_features",feature_con,if_exists="replace",index=False,chunksize=5000)
    feature_con.execute("CREATE INDEX IF NOT EXISTS idx_professional_features ON professional_features(symbol, detected_at, period)")
    feature_con.commit();feature_integrity=feature_con.execute("PRAGMA integrity_check").fetchone()[0];feature_con.close()
    holdrows=cohorts[cohorts.period.eq("holdout")];best=cohorts[cohorts.period.eq("calibration")].sort_values("expectancy_3r_after_0_05r",ascending=False).iloc[0]
    selected_pct=int(best.calibration_percentile_threshold);selected=cohorts[cohorts.calibration_percentile_threshold.eq(selected_pct)].set_index("period").to_dict("index")
    report={"schema":"TP_V5_PROFESSIONAL_POINT_IN_TIME_FEATURE_LAB_1","generated_utc":datetime.now(timezone.utc).isoformat(),"evidence_integrity":integrity_e,"warehouse_integrity":integrity_w,
      "rows":len(df),"features":len(names)-1,"feature_database_integrity":feature_integrity,"ambiguity_policy":"same_minute_ambiguous is a non-win","splits":{"development":"2021-2023","calibration":"2024","holdout":"2025 report-only"},
      "selected_l2":lam,"calibration_log_loss":loss,"selected_calibration_percentile":selected_pct,"selected_cohort_results":selected,
      "holdout_best_report_only":holdrows.sort_values("expectancy_3r_after_0_05r",ascending=False).iloc[0].to_dict(),
      "warning":"Do not tune against holdout_best_report_only. A new final holdout would be required.",
      "files":["chronological_score_cohorts.csv","feature_coefficients.csv","feature_quintile_audit.csv","professional_features.db"]}
    rp=out/"professional_feature_lab_report.json";rp.write_text(json.dumps(report,indent=2,default=str),encoding="utf-8")
    print(f"\nSELECTED COHORT: top {100-selected_pct}% by 2024-fixed score",flush=True)
    for period,m in selected.items():print(f"  {period}: n={m['n']:,} rate={m['rate']:.4%} Wilson={m['wilson_lower']:.4%} exp={m['expectancy_3r_after_0_05r']:+.4f}R",flush=True)
    print(f"REPORT READY: {rp}",flush=True);print(f"INTEGRITY: evidence={integrity_e}, warehouse={integrity_w}, features={feature_integrity}",flush=True)

if __name__=="__main__":main()
