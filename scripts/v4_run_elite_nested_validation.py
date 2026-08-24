import sys,json,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_elite_nested_discovery import validate
p=argparse.ArgumentParser()
p.add_argument("--evidence",default="research_data/v4/context_evidence_v4.db")
p.add_argument("--outdir",default="research_data/v4/elite_discovery_nested")
a=p.parse_args()
r=validate(a.evidence,a.outdir)
print("\n===== V4 ELITE DISCOVERY + NESTED VALIDATION =====")
print("ROWS",r["rows"],"SPLITS",r["splits"])
print("RULES: ELITE",r["elite_rules_discovered"],"GRAND_SLAM",r["grandslam_rules_discovered"])
print("VALIDATION ELITE",json.dumps(r["validation"]["elite"]))
print("VALIDATION GRAND_SLAM",json.dumps(r["validation"]["grandslam"]))
print("FINAL HOLDOUT ELITE",json.dumps(r["final_holdout"]["elite"]))
print("FINAL HOLDOUT GRAND_SLAM",json.dumps(r["final_holdout"]["grandslam"]))
print("PROMOTION STATUS:",r["promotion_status"])
print("REPORT:",str(Path(a.outdir)/"nested_validation_report.json"))
print("FROZEN RULES:",str(Path(a.outdir)/"frozen_rules.json"))
