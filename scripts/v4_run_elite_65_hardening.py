import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_elite_65_hardening import run
p=argparse.ArgumentParser();p.add_argument("--evidence",default="research_data/v4/context_evidence_v4.db");p.add_argument("--out",default="research_data/v4/elite_65_hardening")
a=p.parse_args();r=run(a.evidence,a.out)
print("\n===== V4 ELITE 65% HARDENING =====")
print("ROWS",r["rows"],"SPLITS",r["splits"],"SURVIVOR RULES",r["survivor_rules"])
print("PRECISION FRONTIER")
for k,v in r["precision_frontier"].items():print(k,json.dumps(v))
print("CHOSEN FROZEN SET",r["chosen_frozen_set"])
print("FINAL HOLDOUT 3R",json.dumps(r["final_holdout"]["3R"]))
print("FINAL HOLDOUT 5R",json.dumps(r["final_holdout"]["5R"]))
print("MAX LOSING STREAK 3R",r["final_holdout"]["max_losing_streak_3R"])
print("GATES",json.dumps(r["gates"]))
print("STATUS",r["status"])
print("REPORT",str(Path(a.out)/"elite_65_hardening_report.json"))
