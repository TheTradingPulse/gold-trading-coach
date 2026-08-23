import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_oos_validation import evaluate_oos
p=argparse.ArgumentParser()
p.add_argument("--evidence",default="research_data/v4/evidence_v3.db")
p.add_argument("--train-fraction",type=float,default=.70)
p.add_argument("--min-triggered",type=int,default=25)
p.add_argument("--out",default="research_data/v4/v4_oos_validation.json")
a=p.parse_args()
r=evaluate_oos(a.evidence,a.train_fraction,a.min_triggered)
Path(a.out).parent.mkdir(parents=True,exist_ok=True)
Path(a.out).write_text(json.dumps(r,indent=2),encoding="utf-8")
print(json.dumps(r,indent=2))
print("\nOOS ORDERING:", "PASS" if r["passes_ordering"] else "NEEDS_CALIBRATION")
# This is diagnostic, not an installer failure: bad ordering must be visible, not hidden.
