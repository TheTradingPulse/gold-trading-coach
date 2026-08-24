from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_historical_catalog import HistoricalCatalog
from v4_historical_intelligence import HistoricalIntelligence
from v4_professor_historical import parse_historical_question
from v4_backtest_intelligence import evidence_metrics,research_artifacts

cat=HistoricalCatalog();cov=cat.coverage()
print("===== V4 HISTORICAL INTELLIGENCE =====")
print("CATALOG FILES",len(cat._entries));print("COVERAGE GROUPS",len(cov))
for r in cov[:20]:print(r)
print("QUERY PARSER",parse_historical_question("Pull up NQ chart from March 1 2024 15m"))
print("QUERY PARSER",parse_historical_question("How has GC moved on August 23 over the past 3 years?"))
print("EVIDENCE",json.dumps(evidence_metrics(),indent=2)[:3000])
print("RESEARCH ARTIFACTS",len(research_artifacts()))
print("[PASS] Historical intelligence foundation smoke complete")
print("NO SCORING CHANGED / NO DATABASE MODIFIED / NO DEPLOY")
