from pathlib import Path
import sys, json, time
ROOT=Path(r"C:\TradingPulse")
sys.path.insert(0,str(ROOT))
from core.v4_blind_library import BlindHistoricalLibrary, SYMBOLS
from core.v4_historical_quality import HistoricalQualityRegistry

lib=BlindHistoricalLibrary()
months=[f"{y}-{m:02d}" for y in range(2021,2026) for m in range(1,13)]
total=len(months)*len(SYMBOLS); done=0
manifest={"expected":total,"built":0,"failed":[],"months":{}}
print("===== V4 5-YEAR CANONICAL BUILD =====")
for month in months:
    manifest["months"][month]={}
    for symbol in SYMBOLS:
        done+=1
        try:
            counts=lib.build_canonical_month(month,symbol)
            manifest["built"]+=1; manifest["months"][month][symbol]=counts
            print(f"[{done:03d}/{total}] {month} {symbol} [PASS] 15m={counts['15m']} 1H={counts['1H']} 4H={counts['4H']}")
        except Exception as e:
            manifest["failed"].append({"month":month,"symbol":symbol,"error":str(e)})
            print(f"[{done:03d}/{total}] {month} {symbol} [FAIL] {e}")
report=lib.root/"reports"/"canonical_5y_manifest.json"
report.write_text(json.dumps(manifest,indent=2),encoding="utf-8")
q=HistoricalQualityRegistry(); q.seed_known(SYMBOLS); q.save(lib.root/"reports"/"data_quality_flags.json")
print("MANIFEST:",report)
print("BUILT:",manifest["built"],"FAILED:",len(manifest["failed"]))
raise SystemExit(1 if manifest["failed"] else 0)
