import sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/"core"))
from v4_evidence_analytics import evidence_report,print_report

x=evidence_report()
print_report()
i=x.get("integrity",{})
bad={}
for k in ("bad_scores","missing_normalized","bad_risk","alive_mae_below_stop","realized_below_stop"):
    if i.get(k):
        bad[k]=i[k]
if i.get("rows")!=i.get("unique_keys"):
    bad["duplicates"]=(i.get("rows"),i.get("unique_keys"))
if bad:
    print("FAIL",bad)
    raise SystemExit(1)
print("EVIDENCE V3 3R/5R INTEGRITY PASS")
