import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"core"))
from v4_market_warehouse import MarketWarehouse
from v4_backtest_evidence import EvidenceStore
from v4_learning_loop import LearningStore
wh=MarketWarehouse()
print("WAREHOUSE INTEGRITY:",wh.integrity())
print("COVERAGE:",json.dumps(wh.coverage(),indent=2))
print("EVIDENCE:",json.dumps(EvidenceStore().summary(),indent=2))
print("PROFESSOR LEARNING:",json.dumps(LearningStore().metrics(),indent=2))
