import sys,tempfile
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"core"))
from v4_market_warehouse import MarketWarehouse
from v4_point_in_time import PointInTimeReader
from v4_data_quality import audit_frame
from v4_chart_intelligence import build_chart_packet
from v4_learning_loop import LearningStore
from v4_backtest_evidence import EvidenceStore

def sample():
    idx=pd.date_range("2026-01-01",periods=20,freq="h",tz="UTC")
    return pd.DataFrame({"open":range(100,120),"high":range(101,121),"low":range(99,119),
                         "close":[x+.5 for x in range(100,120)],"volume":100},index=idx)

def test_warehouse_and_point_in_time(tmp_path):
    p=tmp_path/"w.db"; wh=MarketWarehouse(p); df=sample()
    assert wh.upsert("GC","1H",df)==20
    assert wh.upsert("GC","1H",df)==20
    assert len(wh.read("GC","1H"))==20
    cut=df.index[9]
    x=PointInTimeReader(p).candles("GC","1H",cut,500)
    assert len(x)==10 and x.index.max()==cut
    assert wh.integrity()=="ok"

def test_quality_and_packet():
    df=sample(); a=audit_frame(df,"1H"); assert a["bad_ohlc"]==0
    p=build_chart_packet("GC",{"1H":df},as_of=df.index[-1]); assert p["timeframes"]["1H"]["bars"]==20

def test_learning_quarantine(tmp_path):
    s=LearningStore(tmp_path/"l.db"); q=s.log_qa("why?","because","GC"); assert q>0
    h=s.propose_claim("A test claim","test",["source"]); assert s.metrics()["claims"]["PENDING"]==1
    s.review_claim(h,"VERIFIED","test review"); assert s.metrics()["claims"]["VERIFIED"]==1

def test_evidence(tmp_path):
    e=EvidenceStore(tmp_path/"e.db"); e.add(symbol="GC",timeframe="1H",as_of="2026-01-01T00:00:00Z",
      score=9.1,outcome="T1_HIT",realized_r=1.0,mfe=2.0,mae=-0.5)
    s=e.summary("GC",9.0); assert s["observations"]==1
