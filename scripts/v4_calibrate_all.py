import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_calibration_engine import calibrate,save_calibration
p=argparse.ArgumentParser()
p.add_argument("--evidence",default="research_data/v4/evidence_v3.db")
p.add_argument("--out",default="research_data/v4_calibration.json")
p.add_argument("--min-triggered",type=int,default=25)
a=p.parse_args()
r=calibrate(a.evidence,a.min_triggered);save_calibration(r,a.out)
print(json.dumps({"version":r["version"],"rows":r["rows"],"score_monotonic":r["score_monotonic"],
                  "groups":len(r["groups"]),"output":a.out},indent=2))
print("\nBUCKET CALIBRATION")
print(json.dumps(r["bucket_stats"],indent=2))
if not r["score_monotonic"]:
    print("\n[IMPORTANT] Existing raw score buckets are NOT monotonic. Calibration overlay is required.")
