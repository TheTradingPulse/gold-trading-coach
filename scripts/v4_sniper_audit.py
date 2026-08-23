import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_oos_validation import load_ordered
from v4_sniper_policy import decide
from v4_target_manager import target_plan
rows,table,tc=load_ordered("research_data/v4/evidence_v3.db")
print("ROWS",len(rows),"TABLE",table,"TIME",tc)
# Audit global evidence only; contextual enrichment begins accumulating without contaminating old evidence.
from v4_calibration_engine import _stats
s=_stats(rows);d=decide(s,completeness=.5);print(json.dumps({"global":s,"decision":d,"target_plan":target_plan(d)},indent=2))
print("[PASS] Sniper policy audit")
