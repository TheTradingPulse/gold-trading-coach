import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_calibrated_policy import V4CalibratedPolicy
p=V4CalibratedPolicy()
r=p.report
groups=[g for g in r["groups"] if "bucket" in g and g.get("sample_ok")]
tiers={"ELITE":[],"WATCH":[],"RESEARCH":[],"INSUFFICIENT_EVIDENCE":[]}
for g in groups:
    c={"symbol":g["symbol"],"setup_type":g["setup_type"],"direction":g["direction"],
       "score10":9.25 if g["bucket"]=="9+" else 8.7 if g["bucket"]=="8.5-8.9" else 8.2 if g["bucket"]=="8-8.4" else 7.5}
    x=p.classify(c);tiers[x["tier"]].append(x)
print("CALIBRATED TIER COUNTS")
print(json.dumps({k:len(v) for k,v in tiers.items()},indent=2))
for k in ("ELITE","WATCH"):
    print("\n"+k)
    for x in sorted(tiers[k],key=lambda z:(z.get("evidence_score10") or 0),reverse=True)[:20]:
        print(x["explanation"])
print("\n[PASS] Raw 9+ no longer automatically means Elite")
