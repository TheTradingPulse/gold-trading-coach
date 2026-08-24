from __future__ import annotations
import argparse,hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"core"))
from v4_market_warehouse import MarketWarehouse

SYMBOLS=("GC","SI","ES","NQ","YM","RTY","CL","NG")
RULES={"5m":"5min","15m":"15min","1H":"1h","4H":"4h","D":"1D","W":"1W-MON"}
PROVIDER="databento_v5"

def normalize(path):
    x=pd.read_parquet(path);low={str(c).lower():c for c in x.columns}
    if "ts_event" in low:x=x.set_index(low["ts_event"])
    elif not isinstance(x.index,pd.DatetimeIndex):
        c=next((low[k] for k in ("timestamp","datetime","time","date") if k in low),None)
        if c is None:raise ValueError(f"No timestamp in {path}")
        x=x.set_index(c)
    x.index=pd.DatetimeIndex(x.index)
    x.index=x.index.tz_localize("UTC") if x.index.tz is None else x.index.tz_convert("UTC")
    low={str(c).lower():c for c in x.columns};need=("open","high","low","close","volume")
    if not all(k in low for k in need):raise ValueError(f"Missing OHLCV in {path}")
    x=x[[low[k] for k in need]];x.columns=list(need);x=x.sort_index()
    return x[~x.index.duplicated(keep="last")]

def resample(src,rule):
    return src.resample(rule,label="left",closed="left").agg(
      {"open":"first","high":"max","low":"min","close":"last","volume":"sum"}
    ).dropna(subset=["open","high","low","close"])

def digest(paths):
    h=hashlib.sha256()
    for p in paths:h.update(p.name.encode());h.update(str(p.stat().st_size).encode())
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--root",default=".");a=ap.parse_args();root=Path(a.root).resolve()
    raw=root/"research_data/v4/historical_blind/raw";out=root/"research_data/v5";out.mkdir(parents=True,exist_ok=True)
    warehouse_path=out/"databento_v5_warehouse.db";wh=MarketWarehouse(warehouse_path)
    manifest={"version":"DATABENTO_V5_WAREHOUSE_1","provider":PROVIDER,"generated_utc":datetime.now(timezone.utc).isoformat(),
              "source_root":str(raw),"warehouse":str(warehouse_path),"symbols":{},"errors":[]}
    for symbol in SYMBOLS:
        files=sorted(raw.glob(f"*/{symbol}__1m.parquet"))
        print(f"\n{symbol}: found {len(files)} monthly one-minute files",flush=True)
        if len(files)!=60:manifest["errors"].append(f"{symbol}: expected 60 raw months, found {len(files)}")
        parts=[]
        for n,p in enumerate(files,1):
            parts.append(normalize(p))
            if n%12==0:print(f"  loaded {n}/{len(files)} months",flush=True)
        if not parts:continue
        src=pd.concat(parts).sort_index();src=src[~src.index.duplicated(keep="last")]
        rec={"raw_files":len(files),"raw_rows":len(src),"first":str(src.index.min()),"last":str(src.index.max()),
             "source_digest":digest(files),"timeframes":{}}
        for tf,rule in RULES.items():
            frame=resample(src,rule);written=wh.upsert(symbol,tf,frame,provider=PROVIDER,data_symbol=f"{symbol}.v.0")
            rec["timeframes"][tf]={"rows":len(frame),"written":written,"first":str(frame.index.min()),"last":str(frame.index.max())}
            print(f"  {tf}: {written:,} rows",flush=True)
        manifest["symbols"][symbol]=rec
        del src,parts
    manifest["coverage"]=wh.coverage();manifest["integrity"]=wh.integrity();manifest["ready"]=not manifest["errors"] and manifest["integrity"]=="ok"
    p=out/"databento_v5_warehouse_manifest.json";p.write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(f"\nWAREHOUSE READY: {warehouse_path}");print(f"MANIFEST READY: {p}");print(f"INTEGRITY: {manifest['integrity']}")
if __name__=="__main__":main()
