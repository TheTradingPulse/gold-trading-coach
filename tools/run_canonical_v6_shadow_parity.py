from __future__ import annotations

import json
import sqlite3
import sys
import zipfile
from datetime import datetime,timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(r"C:\TradingPulse");sys.path.insert(0,str(ROOT/"core"))
from canonical_professional_zone_detector import DETECTOR_VERSION,detect_professional_zones

WAREHOUSE=ROOT/"research_data"/"v5"/"databento_v5_warehouse.db"
REFERENCE=ROOT/"research_data"/"v6"/"professional_zone_reference.db"
OUT=ROOT/"research_data"/"canonical"/"phase3a"
SYMBOLS=("GC","SI","ES","NQ","YM","RTY","CL","NG");PROVIDER="databento_v5"
FIELDS=("symbol","pattern","direction","base_start","base_end","formed_at","entry_ts","proximal","distal","entry","stop","risk","risk_ticks","base_candles","departure_ratio","breakout","strength_score","time_score","freshness_score","trend_score","curve_score","profit_score","profit_room_r","ota_score","curve_position")


def read_tf(con,symbol,tf):
    q="select timestamp,open,high,low,close,volume from candles where symbol=? and timeframe=? and provider=? order by timestamp"
    x=pd.read_sql_query(q,con,params=(symbol,tf,PROVIDER));x.timestamp=pd.to_datetime(x.timestamp,utc=True);return x.set_index("timestamp")


def same(a,b):
    if pd.isna(a) and pd.isna(b):return True
    try:return bool(np.isclose(float(a),float(b),rtol=1e-10,atol=1e-10,equal_nan=True))
    except:return str(a)==str(b)


def main():
    OUT.mkdir(parents=True,exist_ok=True);wh=sqlite3.connect(f"file:{WAREHOUSE.as_posix()}?mode=ro",uri=True)
    ref=sqlite3.connect(f"file:{REFERENCE.as_posix()}?mode=ro",uri=True);reports=[];examples=[]
    for symbol in SYMBOLS:
        print(f"{symbol}: reconstructing professional zones",flush=True)
        detected=detect_professional_zones(symbol,read_tf(wh,symbol,"5m"),read_tf(wh,symbol,"15m"),read_tf(wh,symbol,"1H"))
        stored=pd.read_sql_query("select * from professional_zones where symbol=?",ref,params=(symbol,))
        a={r["zone_id"]:r for r in detected.to_dict("records")};b={r["zone_id"]:r for r in stored.to_dict("records")}
        missing=sorted(set(b)-set(a));extra=sorted(set(a)-set(b));field_mismatches=0
        for zid in sorted(set(a)&set(b)):
            bad=[f for f in FIELDS if not same(a[zid].get(f),b[zid].get(f))]
            if bad:
                field_mismatches+=1
                if len(examples)<100:examples.append({"symbol":symbol,"zone_id":zid,"fields":bad})
        report={"symbol":symbol,"detected":len(a),"stored":len(b),"missing_ids":len(missing),"extra_ids":len(extra),"field_mismatch_rows":field_mismatches,
                "exact":not missing and not extra and field_mismatches==0}
        reports.append(report);print(f"  detected={len(a):,} stored={len(b):,} exact={report['exact']}",flush=True)
    wh.close();ref.close();exact=all(r["exact"] for r in reports)
    report={"schema":"TP_CANONICAL_V6_SHADOW_PARITY_1","generated_utc":datetime.now(timezone.utc).isoformat(),"detector_version":DETECTOR_VERSION,
            "symbols":reports,"all_symbols_exact":exact,"mismatch_examples":examples,
            "decision":"SHADOW_DETECTOR_PARITY_PROVEN" if exact else "BLOCKED_PARITY_MISMATCH",
            "live_promotion":False,"note":"Exact historical detector parity does not itself prove profitability or authorize live Elite grading."}
    path=OUT/"canonical_v6_shadow_parity.json";path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    registry_path=ROOT/"config"/"tradingpulse_registry.json";registry=json.loads(registry_path.read_text(encoding="utf-8"))
    registry["status"]="CANONICAL_V6_SHADOW_PARITY_PROVEN" if exact else "CANONICAL_V6_SHADOW_PARITY_FAILED"
    registry["production"]["shadow_structure_detector"]="core/canonical_professional_zone_detector.py"
    registry["production"]["shadow_parity"]="PROVEN" if exact else "FAILED"
    registry_path.write_text(json.dumps(registry,indent=2),encoding="utf-8")
    result=Path.home()/"Downloads"/"TradingPulse_Canonical_Phase3A_Result_20260823.zip"
    with zipfile.ZipFile(result,"w",zipfile.ZIP_DEFLATED) as z:
        z.write(path,arcname=path.name);z.write(registry_path,arcname="tradingpulse_registry.json")
    print(f"ALL SYMBOLS EXACT: {exact}")
    print("LIVE PROMOTION: False")
    print(f"RESULT ZIP READY: {result}")
    if not exact:raise SystemExit(2)


if __name__=="__main__":main()
