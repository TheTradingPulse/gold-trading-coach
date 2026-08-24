from __future__ import annotations
import argparse,hashlib,json,math,sqlite3
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd

SYMBOLS=("GC","SI","ES","NQ","YM","RTY","CL","NG")
TICKS={"GC":.1,"SI":.005,"ES":.25,"NQ":.25,"YM":1.,"RTY":.1,"CL":.01,"NG":.001}
PROVIDER="databento_v5";MAX_R=20;SCHEMA="TP_V6_PROFESSIONAL_ZONES_1"

def sid(*x):return hashlib.sha256("|".join(map(str,x)).encode()).hexdigest()[:32]
def atr(x,n=14):
    pc=x.close.shift();tr=pd.concat([x.high-x.low,(x.high-pc).abs(),(x.low-pc).abs()],axis=1).max(axis=1)
    return tr.rolling(n,min_periods=n).mean()
def read_tf(con,symbol,tf):
    q="SELECT timestamp,open,high,low,close,volume FROM candles WHERE symbol=? AND timeframe=? AND provider=? ORDER BY timestamp"
    x=pd.read_sql_query(q,con,params=(symbol,tf,PROVIDER));x.timestamp=pd.to_datetime(x.timestamp,utc=True);return x.set_index("timestamp")
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
def load_raw(root,symbol):
    files=sorted((root/"research_data/v4/historical_blind/raw").glob(f"*/{symbol}__1m.parquet"))
    if len(files)!=60:raise RuntimeError(f"{symbol}: expected 60 one-minute files, found {len(files)}")
    parts=[]
    for n,p in enumerate(files,1):
        parts.append(normalize(p))
        if n%12==0:print(f"  loaded {n}/60 one-minute months",flush=True)
    x=pd.concat(parts).sort_index();return x[~x.index.duplicated(keep="last")]
def known_series(series,duration):
    z=series.copy();z.index=z.index+pd.Timedelta(duration);return z
def prior(s,ts):
    i=s.index.searchsorted(ts,side="right")-1
    return float(s.iloc[i]) if i>=0 and pd.notna(s.iloc[i]) else None

def context_frames(m15,h1):
    m15_ma20=m15.close.ewm(span=20,adjust=False).mean();m15_ma50=m15.close.ewm(span=50,adjust=False).mean()
    trend=pd.DataFrame({"ma20":m15_ma20,"ma50":m15_ma50,"slope":m15_ma20-m15_ma20.shift(3)})
    trend.index=trend.index+pd.Timedelta("15min")
    hi=h1.high.rolling(20,min_periods=20).max();lo=h1.low.rolling(20,min_periods=20).min()
    curve=known_series((h1.close-lo)/(hi-lo).replace(0,np.nan),"1h")
    return trend,curve

def detect_zones(symbol,m5,m15,h1,max_return_bars=2016):
    tick=TICKS[symbol];x=m5.copy();x["atr"]=atr(x);rng=(x.high-x.low).replace(0,np.nan);x["body_ratio"]=(x.close-x.open).abs()/rng
    base_ok=(x.body_ratio<=.5)&(rng<=1.5*x.atr)&x.atr.notna();trend,curve=context_frames(m15,h1)
    hi=x.high.to_numpy(float);lo=x.low.to_numpy(float);op=x.open.to_numpy(float);cl=x.close.to_numpy(float);at=x.atr.to_numpy(float);ok=base_ok.to_numpy(bool);idx=x.index
    rows=[];i=55
    while i<len(x)-10:
        if not ok[i]:i+=1;continue
        start=i;end=i
        while end+1<len(x)-4 and end-start+1<6 and ok[end+1]:
            union=max(hi[start:end+2])-min(lo[start:end+2])
            if union>2*at[start]:break
            end+=1
        count=end-start+1;dep_start=end+1;dep_end=end+3
        zone_hi=float(max(hi[start:end+1]));zone_lo=float(min(lo[start:end+1]));width=zone_hi-zone_lo
        if width<=0 or not np.isfinite(at[start]):i=end+1;continue
        up=float(max(hi[dep_start:dep_end+1])-zone_hi);down=float(zone_lo-min(lo[dep_start:dep_end+1]))
        direction="LONG" if up>down and up>=1.5*width else ("SHORT" if down>up and down>=1.5*width else None)
        if direction is None:i=end+1;continue
        dep_ratio=(up if direction=="LONG" else down)/width
        prior_hi=float(max(hi[max(0,start-20):start]));prior_lo=float(min(lo[max(0,start-20):start]))
        breakout=(max(hi[dep_start:dep_end+1])>prior_hi) if direction=="LONG" else (min(lo[dep_start:dep_end+1])<prior_lo)
        move_out=(dep_ratio>=2 and (cl[dep_end]>zone_hi if direction=="LONG" else cl[dep_end]<zone_lo))
        strength=2 if move_out and breakout else (1 if move_out or breakout else 0)
        if strength==0:i=end+1;continue
        formed=idx[dep_end]+pd.Timedelta("5min");prox=zone_hi if direction=="LONG" else zone_lo;dist=zone_lo if direction=="LONG" else zone_hi
        entry_j=None
        for j in range(dep_end+1,min(len(x),dep_end+1+max_return_bars)):
            if lo[j]<=prox<=hi[j]:entry_j=j;break
        if entry_j is None:i=end+1;continue
        entry_time=idx[entry_j];entry=prox;stop=dist-tick if direction=="LONG" else dist+tick;risk=abs(entry-stop)
        if risk<=0:i=end+1;continue
        # Profit room uses structure known before the zone formed.
        ph=float(max(hi[max(0,start-100):start]));pl=float(min(lo[max(0,start-100):start]))
        room=max(0,(ph-entry)/risk if direction=="LONG" else (entry-pl)/risk);profit=2 if room>=3 else (1 if room>=2 else 0)
        if profit==0:i=end+1;continue
        pos=trend.index.searchsorted(entry_time,side="right")-1
        if pos>=0:
            tr=trend.iloc[pos];aligned=(direction=="LONG" and tr.ma20>tr.ma50 and tr.slope>0) or (direction=="SHORT" and tr.ma20<tr.ma50 and tr.slope<0)
            opposite=(direction=="LONG" and tr.ma20<tr.ma50 and tr.slope<0) or (direction=="SHORT" and tr.ma20>tr.ma50 and tr.slope>0)
            trend_score=2 if aligned else (0 if opposite else 1)
        else:trend_score=1
        cp=prior(curve,entry_time)
        if cp is None:curve_score=.5
        elif direction=="LONG":curve_score=1 if cp<=.33 else (.5 if cp<=.67 else 0)
        else:curve_score=1 if cp>=.67 else (.5 if cp>=.33 else 0)
        time_score=1 if count<=3 else .5;freshness=2;score=strength+time_score+freshness+trend_score+curve_score+profit
        arrival=float(cl[start]-cl[max(0,start-3)]);pattern=("DBR" if arrival<0 else "RBR") if direction=="LONG" else ("RBD" if arrival>0 else "DBD")
        rows.append({"zone_id":sid(symbol,idx[start],idx[end],direction,round(prox,8)),"symbol":symbol,"pattern":pattern,"direction":direction,
          "base_start":idx[start].isoformat(),"base_end":idx[end].isoformat(),"formed_at":formed.isoformat(),"entry_ts":entry_time.isoformat(),
          "proximal":prox,"distal":dist,"entry":entry,"stop":stop,"risk":risk,"risk_ticks":risk/tick,"base_candles":count,
          "departure_ratio":dep_ratio,"breakout":int(breakout),"strength_score":strength,"time_score":time_score,"freshness_score":freshness,
          "trend_score":trend_score,"curve_score":curve_score,"profit_score":profit,"profit_room_r":room,"ota_score":score,"curve_position":cp})
        i=end+1
    return pd.DataFrame(rows)

def replay(zones,raw,max_minutes=14400):
    idx=raw.index;hi=raw.high.to_numpy(float);lo=raw.low.to_numpy(float);out=[]
    for n,r in enumerate(zones.itertuples(index=False),1):
        begin=idx.searchsorted(pd.Timestamp(r.entry_ts),side="left");end=min(len(idx),begin+max_minutes);entered=None
        for j in range(begin,end):
            if lo[j]<=r.entry<=hi[j]:entered=j;break
        if entered is None:out.append((r.zone_id,None,"not_entered",0,0));continue
        verified=0;possible=0;terminal="open"
        for j in range(entered,end):
            fav=(hi[j]-r.entry)/r.risk if r.direction=="LONG" else (r.entry-lo[j])/r.risk
            reached=max(0,min(MAX_R,int(math.floor(fav+1e-10))))
            stophit=lo[j]<=r.stop if r.direction=="LONG" else hi[j]>=r.stop
            if j==entered:
                possible=max(possible,reached)
                if stophit:terminal="stopped";break
                continue
            if stophit:possible=max(possible,reached);terminal="stopped";break
            verified=max(verified,reached);possible=max(possible,verified)
            if verified>=MAX_R:terminal="20r_verified";break
        out.append((r.zone_id,idx[entered].isoformat(),terminal,verified,possible))
        if n%2000==0:print(f"  replayed {n:,}/{len(zones):,} professional zones",flush=True)
    return pd.DataFrame(out,columns=["zone_id","verified_entry_ts","terminal","max_verified_r","max_possible_r"])

def init_db(path):
    c=sqlite3.connect(path);c.executescript("""
    CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS source_runs(run_id TEXT PRIMARY KEY,symbol TEXT,provider TEXT,dataset TEXT,schema_name TEXT,engine_version TEXT,created_at TEXT,status TEXT,source_reference TEXT);
    CREATE TABLE IF NOT EXISTS professional_zones(zone_id TEXT PRIMARY KEY,symbol TEXT,pattern TEXT,direction TEXT,base_start TEXT,base_end TEXT,formed_at TEXT,entry_ts TEXT,proximal REAL,distal REAL,entry REAL,stop REAL,risk REAL,risk_ticks REAL,base_candles INTEGER,departure_ratio REAL,breakout INTEGER,strength_score REAL,time_score REAL,freshness_score REAL,trend_score REAL,curve_score REAL,profit_score REAL,profit_room_r REAL,ota_score REAL,curve_position REAL,verified_entry_ts TEXT,terminal TEXT,max_verified_r INTEGER,max_possible_r INTEGER);
    CREATE TABLE IF NOT EXISTS progress(symbol TEXT PRIMARY KEY,status TEXT,completed_at TEXT,zones INTEGER);
    CREATE INDEX IF NOT EXISTS idx_v6_zone ON professional_zones(symbol,entry_ts,ota_score);
    """);c.execute("INSERT OR REPLACE INTO meta VALUES('schema_version',?)",(SCHEMA,));c.commit();return c
def wilson(w,n,z=1.959963984540054):
    if not n:return None
    p=w/n;d=1+z*z/n;return (p+z*z/(2*n)-z*math.sqrt((p*(1-p)+z*z/(4*n))/n))/d
def summarize(df):
    df.entry_ts=pd.to_datetime(df.entry_ts,utc=True);df["year"]=df.entry_ts.dt.year;df["period"]=np.where(df.year<=2023,"development",np.where(df.year==2024,"calibration",np.where(df.year==2025,"holdout","outside")))
    rows=[]
    for score in (5,6,7,8,9,9.5):
      g=df[(df.ota_score>=score)&df.terminal.ne("not_entered")&df.period.ne("outside")]
      for rr in range(1,MAX_R+1):
       for period,p in g.groupby("period"):
        win=p.max_verified_r.ge(rr);amb=(~win)&p.max_possible_r.ge(rr);loss=(~win)&(~amb)&p.terminal.eq("stopped");opened=(~win)&(~amb)&(~loss)
        w=int(win.sum());a=int(amb.sum());l=int(loss.sum());o=int(opened.sum());n=w+l+a;rate=w/n if n else None
        rows.append({"score_min":score,"rr":rr,"period":period,"n":n,"wins":w,"losses":l,"ambiguous":a,"open":o,"rate":rate,"wilson_lower":wilson(w,n),"expectancy_after_0_05r":((rr+1)*rate-1-.05) if rate is not None else None})
    return pd.DataFrame(rows)
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--root",default=".");a=ap.parse_args();root=Path(a.root).resolve();v6=root/"research_data/v6";v6.mkdir(parents=True,exist_ok=True)
    whp=root/"research_data/v5/databento_v5_warehouse.db";rawroot=root/"research_data/v4/historical_blind/raw";dbp=v6/"professional_zone_reference.db"
    if not whp.exists() or not rawroot.exists():raise SystemExit("V5 warehouse or authoritative raw data missing")
    wh=sqlite3.connect(whp);wi=wh.execute("PRAGMA integrity_check").fetchone()[0];dst=init_db(dbp)
    for symbol in SYMBOLS:
        done=dst.execute("SELECT status FROM progress WHERE symbol=?",(symbol,)).fetchone()
        if done and done[0]=="complete":print(f"\n{symbol}: checkpoint complete; skipping",flush=True);continue
        print(f"\n{symbol}: detecting OTA-style professional zones",flush=True);dst.execute("DELETE FROM professional_zones WHERE symbol=?",(symbol,));dst.commit()
        m5=read_tf(wh,symbol,"5m");m15=read_tf(wh,symbol,"15m");h1=read_tf(wh,symbol,"1H")
        zones=detect_zones(symbol,m5,m15,h1);print(f"  qualified formations with first retest: {len(zones):,}",flush=True)
        raw=load_raw(root,symbol);paths=replay(zones,raw);full=zones.merge(paths,on="zone_id",how="left")
        cols=[r[1] for r in dst.execute("PRAGMA table_info(professional_zones)")]
        dst.executemany(f"INSERT OR REPLACE INTO professional_zones VALUES({','.join('?' for _ in cols)})",[[r.get(c) for c in cols] for r in full.to_dict("records")])
        run=sid(symbol,SCHEMA,datetime.now(timezone.utc).isoformat());dst.execute("INSERT INTO source_runs VALUES(?,?,?,?,?,?,?,?,?)",(run,symbol,"DATABENTO","GLBX.MDP3","ohlcv-1m",SCHEMA,datetime.now(timezone.utc).isoformat(),"complete",str(rawroot)))
        dst.execute("INSERT OR REPLACE INTO progress VALUES(?,?,?,?)",(symbol,"complete",datetime.now(timezone.utc).isoformat(),len(full)));dst.commit();print(f"  CHECKPOINT READY: {symbol}",flush=True)
    wh.close();allz=pd.read_sql_query("SELECT * FROM professional_zones",dst);integrity=dst.execute("PRAGMA integrity_check").fetchone()[0];dst.close()
    summary=summarize(allz);sp=v6/"v6_score_rr_ladder.csv";summary.to_csv(sp,index=False)
    eligible=summary.pivot_table(index=["score_min","rr"],columns="period",values=["expectancy_after_0_05r","n"])
    choices=[]
    for key,row in eligible.iterrows():
        try:
            if row[("n","development")]>=500 and row[("n","calibration")]>=200:
                score=min(row[("expectancy_after_0_05r","development")],row[("expectancy_after_0_05r","calibration")]);choices.append((score,key))
        except KeyError:pass
    selected=max(choices) if choices else None;selected_rows=[]
    if selected:selected_rows=summary[(summary.score_min==selected[1][0])&(summary.rr==selected[1][1])].to_dict("records")
    report={"schema":SCHEMA,"generated_utc":datetime.now(timezone.utc).isoformat(),"warehouse_integrity":wi,"reference_integrity":integrity,"zones":len(allz),"symbols":allz.groupby("symbol").size().to_dict(),
      "ota_scorecard":{"strength":2,"time":1,"freshness":2,"trend_15m":2,"curve_1h":1,"profit_zone":2},"targets_tested":list(range(1,21)),
      "selection":"maximize minimum development/calibration expectancy; 2025 report-only","selected_without_holdout":None if not selected else {"selection_score":selected[0],"score_min":selected[1][0],"rr":selected[1][1],"results":selected_rows},
      "reference_library_integration":{"source_runs":True,"frozen_setup":True,"engine_version":SCHEMA,"auditable_rr_path":True,"similarity_ready":True},
      "warning":"Research only. Do not update production grading until untouched holdout results are reviewed."}
    rp=v6/"v6_professional_zone_report.json";rp.write_text(json.dumps(report,indent=2,default=str),encoding="utf-8")
    print(f"\nV6 PROFESSIONAL ZONES: {len(allz):,}",flush=True);print(f"SELECTED WITHOUT HOLDOUT: {report['selected_without_holdout']}",flush=True);print(f"REPORT READY: {rp}",flush=True);print(f"INTEGRITY: warehouse={wi}, reference={integrity}",flush=True)
if __name__=="__main__":main()

