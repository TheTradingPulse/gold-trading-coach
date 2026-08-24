from __future__ import annotations
import argparse,csv,json,math,sqlite3,sys,zipfile
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_intrabar_resolver import resolve_minutes

def js(v):
    try:return json.loads(v or "{}")
    except:return {}

def f(*values):
    for v in values:
        try:return float(v)
        except (TypeError,ValueError):pass
    return None

def normalize(df):
    x=df.copy();cols={str(c).lower():c for c in x.columns}
    if "ts_event" in cols:x[cols["ts_event"]]=pd.to_datetime(x[cols["ts_event"]],utc=True);x=x.set_index(cols["ts_event"])
    elif not isinstance(x.index,pd.DatetimeIndex):
        c=next((cols[k] for k in ("timestamp","datetime","time","date") if k in cols),None)
        if c is None:raise ValueError("raw file lacks timestamp")
        x[c]=pd.to_datetime(x[c],utc=True);x=x.set_index(c)
    else:
        # Parquet normally preserves a DatetimeIndex. Re-running pd.to_datetime
        # on it can take minutes on Windows/pandas and serves no purpose.
        x.index = x.index.tz_localize("UTC") if x.index.tz is None else x.index.tz_convert("UTC")
    low={str(c).lower():c for c in x.columns};x=x.rename(columns={low[k]:k for k in ("open","high","low","close") if k in low})
    return x.sort_index()

class RawCache:
    def __init__(self,root):self.root=Path(root);self.cache={}
    def load(self,symbol,month):
        key=(symbol,month)
        if key not in self.cache:
            candidates=[self.root/"raw"/month/f"{symbol}__1m.parquet",
                        self.root/"monthly"/month/f"{symbol}__1m.parquet",
                        self.root/"canonical_5y"/month/f"{symbol}__1m.parquet"]
            p=next((p for p in candidates if p.exists()),None)
            self.cache[key]=(normalize(pd.read_parquet(p)) if p else None,p)
        return self.cache[key]

class Canonical15mCache:
    """Resolve replay bar offsets on the real session-aware 15-minute index."""
    def __init__(self,root):self.root=Path(root);self.cache={}
    def load_month(self,symbol,month):
        key=(symbol,month)
        if key not in self.cache:
            candidates=[self.root/"canonical_5y"/month/f"{symbol}__15m.parquet",
                        self.root/"monthly"/month/f"{symbol}__15m.parquet"]
            p=next((p for p in candidates if p.exists()),None)
            self.cache[key]=(normalize(pd.read_parquet(p)) if p else None,p)
        return self.cache[key]
    def offset_time(self,symbol,asof,offset):
        period=asof.tz_localize(None).to_period("M")
        frames=[];paths=[]
        # An outcome can cross a month boundary. Three adjacent months safely
        # cover the existing 240-bar forward horizon and session closures.
        for q in (period-1,period,period+1,period+2):
            df,p=self.load_month(symbol,str(q))
            if df is not None:frames.append(df);paths.append(str(p))
        if not frames:return None,"CANONICAL_FILE_MISSING",paths
        idx=pd.concat(frames).sort_index().index.drop_duplicates()
        matches=idx.get_indexer([asof])
        pos=int(matches[0])
        if pos<0:return None,"CANONICAL_ASOF_MISSING",paths
        target=pos+int(offset)
        if target<0 or target>=len(idx):return None,"CANONICAL_OFFSET_OUT_OF_RANGE",paths
        return idx[target],None,paths

def band(x):
    x=f(x)
    if x is None:return "UNKNOWN"
    if x>10:x/=10
    lo=math.floor(x*2)/2;return f"{lo:.1f}-{lo+.49:.2f}"

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--root",default=".");ap.add_argument("--out",default=None);a=ap.parse_args()
    root=Path(a.root).resolve();stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
    out=Path(a.out).resolve() if a.out else root/"research_data/v4/audits"/f"intrabar_resolution_{stamp}";out.mkdir(parents=True,exist_ok=True)
    db=root/"research_data/v4/context_evidence_v4.db";rawroot=root/"research_data/v4/historical_blind";cache=RawCache(rawroot);canonical=Canonical15mCache(rawroot)
    con=sqlite3.connect(f"file:{db.as_posix()}?mode=ro",uri=True);con.row_factory=sqlite3.Row
    query="select id,symbol,as_of,score10,direction,candidate_json,outcome_json from observations where entered=1 and primary_hit=1 and stop_hit=1"
    results=[];counts=defaultdict(int)
    for row_number,row in enumerate(con.execute(query),start=1):
        r=dict(row);o=js(r["outcome_json"]);c=js(r["candidate_json"])
        bp=o.get("bars_to_primary");bo=o.get("bars_to_outcome")
        try: same=int(bp)==int(bo)
        except:same=bool(o.get("same_bar_ambiguous"))
        if not same:continue
        counts["eligible_15m_ambiguous"]+=1
        asof=pd.Timestamp(r["as_of"]);asof=asof.tz_localize("UTC") if asof.tzinfo is None else asof.tz_convert("UTC")
        be=int(o.get("bars_to_entry") or 0);bt=int(o.get("bars_to_outcome") or 0)
        symbol=str(r["symbol"]).upper()
        bar_start,canonical_error,canonical_paths=canonical.offset_time(symbol,asof,1+be+bt)
        rec={"id":r["id"],"symbol":r["symbol"],"as_of":r["as_of"],"score_band":band(r["score10"]),
             "bar_start":str(bar_start) if bar_start is not None else None,
             "canonical_error":canonical_error,"canonical_files":";".join(canonical_paths)}
        if canonical_error:
            rec["result"]=canonical_error;counts[rec["result"]]+=1;results.append(rec);continue
        bar_end=bar_start+pd.Timedelta(minutes=15)
        month=bar_start.strftime("%Y-%m")
        cache_key=(symbol,month)
        was_cached=cache_key in cache.cache
        df,path=cache.load(symbol,month)
        if not was_cached:
            print(f"Loaded {symbol} {month}: {path or 'MISSING'}",flush=True)
        if row_number % 1000 == 0:
            print(f"Processed {row_number:,} overlapping outcomes; {counts['eligible_15m_ambiguous']:,} same-bar cases",flush=True)
        entry=f(c.get("projected_entry"),c.get("entry"));stop=f(c.get("projected_stop"),c.get("stop"));target=f(o.get("primary_target"))
        rec["raw_file"]=str(path) if path else None
        if df is None:rec["result"]="RAW_FILE_MISSING";counts[rec["result"]]+=1;results.append(rec);continue
        if None in (entry,stop,target):rec["result"]="LEVELS_MISSING";counts[rec["result"]]+=1;results.append(rec);continue
        mins=df.loc[(df.index>=bar_start)&(df.index<bar_end)]
        if mins.empty:rec["result"]="MINUTES_MISSING";counts[rec["result"]]+=1;results.append(rec);continue
        resolved=resolve_minutes(mins,r["direction"],entry,stop,target,already_entered=bt>0)
        rec.update(resolved.to_dict());rec["minute_rows"]=len(mins);counts[resolved.result]+=1;results.append(rec)
    con.close()
    groups=defaultdict(lambda:defaultdict(int))
    for r in results:
        for key in (r["symbol"],r["score_band"],r["symbol"]+"|"+r["score_band"]):groups[key][r["result"]]+=1
    report={"version":"TP_INTRABAR_RESOLUTION_1","generated_utc":datetime.now(timezone.utc).isoformat(),
            "source_db":str(db),"raw_root":str(rawroot),"policy":"same-minute target and stop remains ambiguous; stop-first is loss",
            "counts":dict(counts),"groups":{k:dict(v) for k,v in sorted(groups.items())}}
    (out/"intrabar_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    if results:
        keys=sorted({k for r in results for k in r})
        with (out/"intrabar_rows.csv").open("w",newline="",encoding="utf-8") as h:w=csv.DictWriter(h,fieldnames=keys);w.writeheader();w.writerows(results)
    lines=["Trading Pulse One-Minute Intrabar Resolution","",*(f"{k}: {v}" for k,v in sorted(counts.items()))]
    (out/"SUMMARY.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    z=out.with_suffix(".zip")
    with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as q:
        for p in out.iterdir():q.write(p,p.name)
    print("\n".join(lines));print(f"ZIP READY: {z}")
if __name__=="__main__":main()
