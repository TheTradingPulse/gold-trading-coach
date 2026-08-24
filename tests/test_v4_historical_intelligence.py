import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"core"))
import pandas as pd
from v4_historical_catalog import HistoricalCatalog
from v4_historical_intelligence import HistoricalIntelligence
from v4_professor_historical import parse_historical_question
from v4_backtest_intelligence import wilson_low

def _write(root,month,sym="NQ"):
 p=root/month;p.mkdir(parents=True,exist_ok=True);idx=pd.date_range(month+"-01",periods=20,freq="15min",tz="UTC");df=pd.DataFrame({"open":range(100,120),"high":range(101,121),"low":range(99,119),"close":[x+.5 for x in range(100,120)],"volume":1},index=idx);df.to_pickle(p/f"{sym}__15m.pkl")
def test_catalog_and_chart(tmp_path):
 _write(tmp_path,"2024-03");c=HistoricalCatalog([tmp_path]);assert len(c.entries("NQ","15m"))==1;r=HistoricalIntelligence(c).chart("NQ","2024-03-01","15m");assert len(r["bars"])==20

def test_asof_blocks_future(tmp_path):
 _write(tmp_path,"2024-03");r=HistoricalIntelligence(HistoricalCatalog([tmp_path])).chart("NQ","2024-03-01","15m",as_of="2024-03-01T01:00:00Z");assert len(r["bars"])==5

def test_parser():
 r=parse_historical_question("Pull up NQ chart from March 1 2024 15m");assert r["intent"]=="chart" and r["symbol"]=="NQ" and r["date"]=="2024-03-01"

def test_wilson_conservative():assert 0 < wilson_low(65,100) < .65
