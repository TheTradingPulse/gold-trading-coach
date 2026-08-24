from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import re
import pandas as pd

TF_ALIASES={"1m":"1m","1min":"1m","15m":"15m","15min":"15m","1h":"1H","60m":"1H","4h":"4H","240m":"4H","d":"D","1d":"D"}
FILE_RE=re.compile(r"^(?P<symbol>[A-Za-z0-9]+)__(?P<tf>1m|15m|1H|4H|D)\.(?:parquet|pkl)$",re.I)

@dataclass(frozen=True)
class CatalogEntry:
    symbol:str; timeframe:str; path:str; month:str|None; bytes:int; modified:float
    def to_dict(self): return asdict(self)

class HistoricalCatalog:
    """Provider-neutral, read-only catalog over TradingPulse historical files."""
    def __init__(self, roots=None):
        self.roots=[Path(x) for x in (roots or ["research_data/v4/historical_blind","research_data/history"])]
        self._entries=[]; self.refresh()
    def refresh(self):
        out=[]
        for root in self.roots:
            if not root.exists(): continue
            for p in root.rglob("*"):
                if not p.is_file(): continue
                m=FILE_RE.match(p.name)
                if not m: continue
                month=next((part for part in p.parts if re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])",part)),None)
                tf=TF_ALIASES.get(m.group("tf").lower(),m.group("tf"))
                st=p.stat();out.append(CatalogEntry(m.group("symbol").upper(),tf,str(p),month,st.st_size,st.st_mtime))
        self._entries=sorted(out,key=lambda x:(x.symbol,x.timeframe,x.month or "",x.path));return self
    def entries(self,symbol=None,timeframe=None):
        s=symbol.upper() if symbol else None; tf=TF_ALIASES.get(str(timeframe).lower(),timeframe) if timeframe else None
        return [x for x in self._entries if (not s or x.symbol==s) and (not tf or x.timeframe==tf)]
    def coverage(self):
        rows=[]
        for (s,tf),grp in __import__('itertools').groupby(self._entries,key=lambda x:(x.symbol,x.timeframe)):
            g=list(grp); months=sorted({x.month for x in g if x.month})
            rows.append({"symbol":s,"timeframe":tf,"files":len(g),"months":len(months),"first_month":months[0] if months else None,"last_month":months[-1] if months else None,"mb":round(sum(x.bytes for x in g)/1048576,2)})
        return rows

def _normalize(df):
    x=df.copy()
    if "ts_event" in x.columns: x=x.set_index("ts_event")
    elif "timestamp" in x.columns: x=x.set_index("timestamp")
    x.index=pd.to_datetime(x.index,utc=True,errors="coerce");x=x[~x.index.isna()]
    x=x.rename(columns={c:str(c).lower() for c in x.columns})
    need=["open","high","low","close","volume"]
    for c in need:
        if c not in x.columns: x[c]=0.0 if c=="volume" else float("nan")
        x[c]=pd.to_numeric(x[c],errors="coerce")
    return x[need].dropna(subset=["open","high","low","close"]).sort_index()

def read_entry(entry):
    p=Path(entry.path)
    return _normalize(pd.read_parquet(p) if p.suffix.lower()==".parquet" else pd.read_pickle(p))
