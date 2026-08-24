import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'core'))
import pandas as pd
from v4_contextual_features import build
from v4_contextual_similarity import similarity,stats
from v4_context_evidence import write,load

def frame(n=100):
    i=pd.date_range('2026-01-01',periods=n,freq='15min',tz='UTC');c=[100+x*.1 for x in range(n)]
    return pd.DataFrame({'open':c,'high':[x+.2 for x in c],'low':[x-.2 for x in c],'close':c,'volume':[1]*n},index=i)
def test_point_in_time_features():
    c={'symbol':'NQ','zone_type':'demand','direction':'LONG','setup_score':91,'projected_entry':100,'projected_stop':99,'projected_rr':3.2,'reasons':['Higher-timeframe context contributes 7.0/10 (2/3 aligned)']}
    f=build(c,{}, {'15m':frame(),'1H':frame(),'4H':frame(),'D':frame()},'2026-01-02T15:00:00Z')
    assert f['symbol']=='NQ' and f['trend_1h']=='bullish' and f['session_utc']=='UTC_12_18' and f['reason_htf']==7.0
def test_missing_not_fabricated():
    f=build({'symbol':'GC','direction':'LONG'},None,{},'2026-01-01T00:00:00Z')
    assert f['zone_quality'] is None and f['trend_1h'] is None
def test_identity_blocks_false_comparable():
    a={'symbol':'NQ','setup_type':'supply','direction':'SHORT'};b={'symbol':'GC','setup_type':'supply','direction':'SHORT'}
    assert similarity(a,b)==0
def test_context_store(tmp_path):
    p=tmp_path/'c.db';r={'symbol':'GC','replay_timeframe':'15m','as_of':'2026-01-01','setup_id':'x','setup_type':'demand','direction':'LONG','grade':'A','lifecycle':'ACTIVE','candidate_payload':{'setup_score':90},'market_state':{}}
    o={'entered':True,'primary_hit':True,'stretch_hit':False,'stop_hit':False,'realized_r':3,'mfe_r':3.2,'mae_r':-.4}
    assert write(p,r,o,{'symbol':'GC','setup_type':'demand','direction':'LONG'})
    x=load(p);assert len(x)==1 and x[0]['_features']['symbol']=='GC' and stats(x)['hit_3r']==1
