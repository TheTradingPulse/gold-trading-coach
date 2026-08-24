import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_temporal_regime_sniper import run
p=argparse.ArgumentParser()
p.add_argument("--evidence",default="research_data/v4/context_evidence_v4.db")
p.add_argument("--out",default="research_data/v4/temporal_regime_sniper")
a=p.parse_args()
r=run(a.evidence,a.out)
print("\n===== V4 TEMPORAL REGIME SNIPER =====")
print("ROWS",r["rows"],"SPLITS",r["splits"])
print("RULES",r["rules"])
print("VALIDATION ELITE",json.dumps(r["validation"]["elite"]))
print("VALIDATION GRAND_SLAM",json.dumps(r["validation"]["grand_slam"]))
print("FINAL HOLDOUT ELITE",json.dumps(r["final_holdout"]["elite"]))
print("FINAL HOLDOUT GRAND_SLAM",json.dumps(r["final_holdout"]["grand_slam"]))
print("TARGETS",json.dumps(r["targets"]))
print("PROMOTION",json.dumps(r["promotion"]))
print("REPORT",str(Path(a.out)/"temporal_regime_report.json"))
