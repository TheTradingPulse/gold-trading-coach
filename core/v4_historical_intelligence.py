from __future__ import annotations
from dataclasses import dataclass,asdict
import math
import pandas as pd
from v4_historical_catalog import HistoricalCatalog,read_entry,TF_ALIASES

@dataclass(frozen=True)
class Provenance:
    provider:str; symbol:str; timeframe:str; start:str|None; end:str|None; rows:int; files:int
    def to_dict(self):return asdict(self)

class HistoricalIntelligence:
    """Deterministic historical facts. Never generates or guesses market statistics."""
    def __init__(self,catalog=None):self.catalog=catalog or HistoricalCatalog()
    def _load(self,symbol,timeframe,start=None,end=None,as_of=None):
        symbol=symbol.upper();tf=TF_ALIASES.get(str(timeframe).lower(),timeframe)
        st=pd.Timestamp(start,tz="UTC") if start and pd.Timestamp(start).tzinfo is None else (pd.Timestamp(start).tz_convert("UTC") if start else None)
        en=pd.Timestamp(end,tz="UTC") if end and pd.Timestamp(end).tzinfo is None else (pd.Timestamp(end).tz_convert("UTC") if end else None)
        ao=pd.Timestamp(as_of,tz="UTC") if as_of and pd.Timestamp(as_of).tzinfo is None else (pd.Timestamp(as_of).tz_convert("UTC") if as_of else None)
        cutoff=min([x for x in (en,ao) if x is not None],default=None)
        frames=[];used=[]
        for e in self.catalog.entries(symbol,tf):
            if e.month:
                ms=pd.Timestamp(e.month+"-01",tz="UTC");me=ms+pd.offsets.MonthBegin(1)
                if st is not None and me<=st:continue
                if cutoff is not None and ms>cutoff:continue
            try: frames.append(read_entry(e));used.append(e)
            except Exception: continue
        if not frames:return pd.DataFrame(columns=["open","high","low","close","volume"]),[]
        x=pd.concat(frames);x=x[~x.index.duplicated(keep="last")].sort_index()
        if st is not None:x=x.loc[x.index>=st]
        if cutoff is not None:x=x.loc[x.index<=cutoff]
        return x,used
    def chart(self,symbol,date,timeframe="15m",start_time=None,end_time=None,as_of=None):
        day=pd.Timestamp(date).date();start=pd.Timestamp(str(day),tz="UTC");end=start+pd.Timedelta(days=1)-pd.Timedelta(microseconds=1)
        if start_time:start=pd.Timestamp(f"{day} {start_time}",tz="UTC")
        if end_time:end=pd.Timestamp(f"{day} {end_time}",tz="UTC")
        x,used=self._load(symbol,timeframe,start,end,as_of)
        prov=Provenance("historical_library",symbol.upper(),timeframe,x.index.min().isoformat() if len(x) else None,x.index.max().isoformat() if len(x) else None,len(x),len(used))
        return {"kind":"chart","symbol":symbol.upper(),"date":str(day),"timeframe":timeframe,"bars":x.reset_index().rename(columns={x.index.name or "index":"timestamp"}).to_dict("records"),"provenance":prov.to_dict()}
    def date_history(self,symbol,month,day,years=5,timeframe="1m",through_year=None):
        end_year=int(through_year or pd.Timestamp.now(tz="UTC").year-1);start_year=end_year-int(years)+1; sessions=[]
        for y in range(start_year,end_year+1):
            try:d=pd.Timestamp(year=y,month=int(month),day=int(day),tz="UTC")
            except ValueError:continue
            x,used=self._load(symbol,timeframe,d,d+pd.Timedelta(days=1)-pd.Timedelta(microseconds=1))
            if not len(x):continue
            o=float(x.open.iloc[0]);c=float(x.close.iloc[-1]);hi=float(x.high.max());lo=float(x.low.min())
            sessions.append({"date":str(d.date()),"open":o,"close":c,"return_pct":round((c/o-1)*100,4),"range_pct":round((hi-lo)/o*100,4),"direction":"UP" if c>o else ("DOWN" if c<o else "FLAT"),"bars":len(x)})
        ups=sum(s["direction"]=="UP" for s in sessions);downs=sum(s["direction"]=="DOWN" for s in sessions)
        return {"kind":"date_history","symbol":symbol.upper(),"month":int(month),"day":int(day),"requested_years":years,"sessions":sessions,"summary":{"n":len(sessions),"up":ups,"down":downs,"up_pct":round(100*ups/len(sessions),1) if sessions else None,"avg_return_pct":round(sum(s["return_pct"] for s in sessions)/len(sessions),4) if sessions else None,"avg_range_pct":round(sum(s["range_pct"] for s in sessions)/len(sessions),4) if sessions else None},"provenance":{"provider":"historical_library","years_examined":[start_year,end_year],"timeframe":timeframe}}
    def daily_fingerprint(self,symbol,date,timeframe="15m",as_of=None):
        r=self.chart(symbol,date,timeframe,as_of=as_of);b=r["bars"]
        if len(b)<10:return {"kind":"fingerprint","symbol":symbol.upper(),"date":str(date),"available":False,"bars":len(b),"provenance":r["provenance"]}
        x=pd.DataFrame(b); c=x.close.astype(float);h=x.high.astype(float);l=x.low.astype(float);o=float(x.open.iloc[0]);last=float(c.iloc[-1]);ret=(last/o-1)*100;rng=(h.max()-l.min())/o*100
        half=max(2,len(c)//2);mom=(last/float(c.iloc[-half])-1)*100
        tr=pd.concat([(h-l),(h-c.shift(1)).abs(),(l-c.shift(1)).abs()],axis=1).max(axis=1);atr=float(tr.tail(min(14,len(tr))).mean())
        return {"kind":"fingerprint","symbol":symbol.upper(),"date":str(date),"available":True,"features":{"return_pct":round(ret,5),"range_pct":round(rng,5),"momentum_pct":round(mom,5),"atr_pct":round(atr/last*100,5) if last else None,"close_location":round((last-l.min())/(h.max()-l.min()),5) if h.max()>l.min() else .5},"bars":len(x),"provenance":r["provenance"]}
    def similar_days(self,symbol,date,years=5,timeframe="15m",limit=20,as_of=None):
        target=self.daily_fingerprint(symbol,date,timeframe,as_of); 
        if not target.get("available"):return {"kind":"similar_days","target":target,"matches":[],"reason":"target date unavailable"}
        td=pd.Timestamp(date,tz="UTC") if pd.Timestamp(date).tzinfo is None else pd.Timestamp(date).tz_convert("UTC");start=td-pd.DateOffset(years=years);x,_=self._load(symbol,timeframe,start,td-pd.Timedelta(days=1))
        matches=[];keys=("return_pct","range_pct","momentum_pct","atr_pct","close_location");tv=target["features"]
        for d,g in x.groupby(x.index.date):
            if len(g)<10:continue
            o=float(g.open.iloc[0]);last=float(g.close.iloc[-1]);hi=float(g.high.max());lo=float(g.low.min());half=max(2,len(g)//2);tr=pd.concat([(g.high-g.low),(g.high-g.close.shift(1)).abs(),(g.low-g.close.shift(1)).abs()],axis=1).max(axis=1)
            f={"return_pct":(last/o-1)*100,"range_pct":((hi-lo)/o*100),"momentum_pct":(last/float(g.close.iloc[-half])-1)*100,"atr_pct":float(tr.tail(min(14,len(tr))).mean())/last*100 if last else None,"close_location":(last-lo)/(hi-lo) if hi>lo else .5}
            diffs=[]
            for k in keys:
                a=tv.get(k);b=f.get(k)
                if a is None or b is None:continue
                scale=max(abs(float(a)),abs(float(b)),.25);diffs.append(abs(float(a)-float(b))/scale)
            sim=max(0.0,1.0-sum(diffs)/len(diffs)) if diffs else 0.0
            matches.append({"date":str(d),"similarity":round(sim,4),"features":{k:round(float(v),5) if v is not None else None for k,v in f.items()}})
        matches.sort(key=lambda z:z["similarity"],reverse=True)
        return {"kind":"similar_days","target":target,"matches":matches[:int(limit)],"provenance":{"provider":"historical_library","lookback_years":years,"timeframe":timeframe,"candidate_sessions":len(matches)}}
