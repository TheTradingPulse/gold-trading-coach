import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_walkforward_optimizer import optimize
p=argparse.ArgumentParser()
p.add_argument("--evidence",default="research_data/v4/evidence_v3.db")
p.add_argument("--folds",type=int,default=5)
p.add_argument("--final-holdout",type=float,default=.15)
p.add_argument("--out",default="research_data/v4/v4_walkforward_report.json")
a=p.parse_args();r=optimize(a.evidence,a.folds,a.final_holdout)
Path(a.out).parent.mkdir(parents=True,exist_ok=True);Path(a.out).write_text(json.dumps(r,indent=2),encoding="utf-8")
print(json.dumps(r,indent=2))
print("\nPROMOTION STATUS:", "READY_FOR_NEXT_STAGE" if r["promotion_ready"] else "KEEP_RESEARCH_ONLY")
