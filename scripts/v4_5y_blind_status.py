from pathlib import Path
import json
root=Path(r"C:\TradingPulse\research_data\v4")
print("===== V4 5-YEAR BLIND STATUS =====")
for p in [
 root/"historical_blind"/"reports"/"databento_2021_2025_final_audit.json",
 root/"historical_blind"/"reports"/"canonical_5y_manifest.json",
 root/"historical_blind"/"reports"/"data_quality_flags.json",
 root/"five_year_blind_validation"/"blind_validation_summary.json",
]:
    print(("PASS " if p.exists() else "MISS "),p)
    if p.exists() and p.suffix==".json":
        try:
            x=json.loads(p.read_text(encoding="utf-8"))
            for k in ("expected","valid","built","failed","rows","primary_3r","stretch_5r"):
                if k in x: print(" ",k,":",x[k])
        except Exception: pass
print("READ ONLY - NOTHING MODIFIED")
