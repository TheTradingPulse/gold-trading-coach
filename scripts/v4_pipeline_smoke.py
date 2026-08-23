import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_candidate_intelligence import enrich_candidate
samples=[
 {"symbol":"GC","setup_type":"demand","direction":"LONG","score10":9.4},
 {"symbol":"NQ","setup_type":"supply","direction":"SHORT","score10":7.5},
 {"symbol":"YM","setup_type":"demand","direction":"LONG","score10":8.2},
]
for s in samples:
    r=enrich_candidate(s)
    print(json.dumps({"input":s,"tier":r["v4_scoring"]["tier"],
      "calibrated":r["v4_scoring"]["calibrated_score10"],
      "professor":r["professor_chart_context"]["evidence_explanation"]},indent=2))
print("[PASS] Candidate -> calibrated policy -> Professor context pipeline")
