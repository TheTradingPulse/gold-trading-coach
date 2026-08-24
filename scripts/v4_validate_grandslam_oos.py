import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_grandslam_oos_validator import validate

p=argparse.ArgumentParser(description="Strict chronological OOS validation for V4 Grand Slam scoring.")
p.add_argument("--evidence",default="research_data/v4/context_evidence_v4.db")
p.add_argument("--train-fraction",type=float,default=.70)
p.add_argument("--out",default="research_data/v4/grandslam_oos/grandslam_oos_report.json")
a=p.parse_args()
r=validate(a.evidence,a.train_fraction,a.out)
print("\n===== V4 GRAND SLAM OOS VALIDATION =====")
print("ROWS",r["rows"],"TRAIN",r["train_rows"],"OOS",r["oos_rows"])
for t,s in r["tiers"].items():
    print(t, json.dumps(s))
print("ORDERED 3R:",r["ordered_3r"],"ORDERED 5R:",r["ordered_5r"])
print("ELITE GATE:",r["elite_gate_pass"])
print("GRAND SLAM ADEQUATE OOS SAMPLE:",r["grandslam_has_adequate_oos_sample"])
print("GRAND SLAM GATE:",r["grandslam_gate_pass"])
print("PROMOTION STATUS:",r["promotion_status"])
print("REPORT:",a.out)
print("\nNOTE: No scoring thresholds are changed by this validator.")
