from __future__ import annotations

import json
import sys
import zipfile
from datetime import datetime,timezone
from pathlib import Path

import pandas as pd

ROOT=Path(r"C:\TradingPulse");sys.path.insert(0,str(ROOT/"core"));sys.path.insert(0,str(ROOT/"analysis"))
from canonical_adapters import from_live_candidate
from canonical_professional_zone_detector import DETECTOR_VERSION,detect_professional_zones
from instruments import get_enabled_symbols
from market_data_provider import fetch_market_data,prefetch_market_data
from market_state_builder import build_market_state
from setup_candidate_engine import build_setup_candidates

OUT=ROOT/"research_data"/"canonical"/"phase3b"
DURATIONS={"5m":pd.Timedelta("5min"),"15m":pd.Timedelta("15min"),"1H":pd.Timedelta("1h")}


def closed(frame,tf,cutoff):
    if frame is None or frame.empty:return frame
    x=frame.copy();x.index=pd.to_datetime(x.index,utc=True)
    return x[x.index+DURATIONS[tf] <= cutoff]


def zone_summary(frame,current_price,cutoff):
    if frame is None or frame.empty:return []
    x=frame.copy();x["entry_ts"]=pd.to_datetime(x.entry_ts,utc=True)
    recent=x[x.entry_ts>=cutoff-pd.Timedelta("14d")].sort_values("entry_ts",ascending=False).head(30)
    rows=[]
    for r in recent.to_dict("records"):
        distance=abs(float(current_price)-float(r["entry"])) if current_price is not None else None
        rows.append({k:r.get(k) for k in ("zone_id","symbol","pattern","direction","formed_at","entry_ts","entry","stop","risk","ota_score","profit_room_r")}|{"distance_points":distance})
    return rows


def main():
    OUT.mkdir(parents=True,exist_ok=True);snapshot=pd.Timestamp.now(tz="UTC");safe_cutoff=snapshot-pd.Timedelta("15min")
    reports=[];all_v6=[];all_v3=[]
    for symbol in get_enabled_symbols():
        print(f"{symbol}: fetching closed reference snapshot",flush=True)
        try:
            prefetch_market_data(symbol,["5m","15m","1H"])
            m5=closed(fetch_market_data(symbol,"5m",limit=20000),"5m",safe_cutoff)
            m15=closed(fetch_market_data(symbol,"15m",limit=10000),"15m",safe_cutoff)
            h1=closed(fetch_market_data(symbol,"1H",limit=5000),"1H",safe_cutoff)
            if any(x is None or len(x)<100 for x in (m5,m15,h1)):raise RuntimeError("insufficient closed snapshot history")
            v6=detect_professional_zones(symbol,m5,m15,h1)
            v6_prev=detect_professional_zones(symbol,m5.iloc[:-1],m15,h1) if len(m5)>1 else v6.iloc[0:0]
            stable=set(v6_prev.zone_id).issubset(set(v6.zone_id));price=float(m5.close.iloc[-1])
            recent=zone_summary(v6,price,safe_cutoff);all_v6.extend(recent)
            # Existing dashboard path. Failures are recorded, not hidden.
            state=build_market_state(symbol);v3=build_setup_candidates(state)
            v3_rows=[]
            for candidate in v3:
                setup=from_live_candidate(candidate)
                row=setup.to_dict();row["validation_errors"]=setup.validate();v3_rows.append(row)
            all_v3.extend(v3_rows)
            report={"symbol":symbol,"snapshot_utc":snapshot.isoformat(),"safe_cutoff_utc":safe_cutoff.isoformat(),
                    "closed_bars":{"5m":len(m5),"15m":len(m15),"1H":len(h1)},"v6_detected":len(v6),
                    "v6_recent_14d":len(recent),"v3_candidates":len(v3_rows),"prior_closed_ids_stable":stable,
                    "v6_recent_directions":dict(pd.Series([r["direction"] for r in recent]).value_counts()) if recent else {},
                    "v3_directions":dict(pd.Series([r["direction"] for r in v3_rows]).value_counts()) if v3_rows else {},"error":None}
            print(f"  V6 recent={len(recent)} V3 candidates={len(v3_rows)} IDs stable={stable}",flush=True)
        except Exception as exc:
            report={"symbol":symbol,"snapshot_utc":snapshot.isoformat(),"error":str(exc),"prior_closed_ids_stable":False}
            print(f"  ERROR: {exc}",flush=True)
        reports.append(report)
    successful=[r for r in reports if not r.get("error")];all_stable=bool(successful) and all(r["prior_closed_ids_stable"] for r in successful)
    report={"schema":"TP_CANONICAL_LIVE_SHADOW_1","generated_utc":datetime.now(timezone.utc).isoformat(),
            "detector_version":DETECTOR_VERSION,"provider":"Yahoo continuous futures reference data",
            "execution_eligible":False,"symbols":reports,"successful_symbols":len(successful),"all_successful_ids_stable":all_stable,
            "live_promotion":False,"decision":"SHADOW_OBSERVATION_ONLY",
            "interpretation":"V3/V6 counts are not expected to match because detector definitions differ. This run checks operability and temporal stability."}
    (OUT/"canonical_live_shadow_report.json").write_text(json.dumps(report,indent=2,default=str),encoding="utf-8")
    pd.DataFrame(all_v6).to_csv(OUT/"v6_recent_shadow_setups.csv",index=False)
    pd.DataFrame(all_v3).to_json(OUT/"v3_live_candidate_snapshot.json",orient="records",indent=2)
    registry_path=ROOT/"config"/"tradingpulse_registry.json";registry=json.loads(registry_path.read_text(encoding="utf-8"))
    registry["status"]="CANONICAL_V6_LIVE_SHADOW_OPERATIONAL" if len(successful)==len(reports) and all_stable else "CANONICAL_V6_LIVE_SHADOW_PARTIAL"
    registry["production"]["live_shadow_last_run"]={"successful_symbols":len(successful),"total_symbols":len(reports),"ids_stable":all_stable}
    registry_path.write_text(json.dumps(registry,indent=2),encoding="utf-8")
    result=Path.home()/"Downloads"/"TradingPulse_Canonical_Phase3B_Result_20260823.zip"
    with zipfile.ZipFile(result,"w",zipfile.ZIP_DEFLATED) as z:
        for name in ("canonical_live_shadow_report.json","v6_recent_shadow_setups.csv","v3_live_candidate_snapshot.json"):
            z.write(OUT/name,arcname=name)
        z.write(registry_path,arcname="tradingpulse_registry.json")
    print(f"SUCCESSFUL SYMBOLS: {len(successful)}/{len(reports)}")
    print(f"CLOSED-CANDLE IDS STABLE: {all_stable}")
    print("LIVE PROMOTION: False")
    print(f"RESULT ZIP READY: {result}")


if __name__=="__main__":main()
