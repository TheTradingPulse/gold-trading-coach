from __future__ import annotations
from v4_canonical_replay import WarehouseMarketStateAdapter,candidate_record
from v4_outcome_engine import evaluate_outcome
from v4_contextual_features import build
from v4_context_evidence import write
from v4_score_contract import score10,tier

class ContextualBacktester:
    def __init__(self,warehouse="research_data/v4/market_warehouse.db",evidence="research_data/v4/context_evidence_v4.db",provider="yahoo"):
        self.adapter=WarehouseMarketStateAdapter(warehouse,provider);self.wh=self.adapter.wh;self.evidence=evidence;self.provider=provider
    def _frames(self,symbol,asof):
        out={}
        for tf,limit in (("15m",220),("1H",220),("4H",160),("D",120)):
            try:out[tf]=self.wh.read(symbol,tf,as_of=asof,limit=limit,provider=self.provider).drop(columns=["provider"],errors="ignore")
            except:out[tf]=None
        return out
    def run_symbol(self,symbol,timeframe="15m",warmup=250,step=16,future_bars=240,min_score10=None,research_tier=None,max_events=None):
        base=self.wh.read(symbol,timeframe,provider=self.provider);summary={"symbol":symbol,"timestamps":0,"candidates":0,"stored":0,"duplicates":0,"errors":0}
        for n,i in enumerate(range(warmup,len(base)-1,max(1,step))):
            if max_events is not None and n>=max_events:break
            summary["timestamps"]+=1;asof=base.index[i]
            try:
                state,candidates=self.adapter.candidates(symbol,asof);future=base.iloc[i+1:i+1+future_bars];frames=self._frames(symbol,asof)
                for c in candidates:
                    if min_score10 is not None and score10(c)<min_score10:continue
                    if research_tier and tier(c)!=research_tier:continue
                    r=candidate_record(symbol,asof,state,c);r["replay_timeframe"]=timeframe;summary["candidates"]+=1
                    outcome=evaluate_outcome(r,future,future_bars);ctx=build(r["candidate_payload"],state,frames,asof)
                    if write(self.evidence,r,outcome,ctx,self.provider):summary["stored"]+=1
                    else:summary["duplicates"]+=1
            except Exception as e:
                summary["errors"]+=1
                if summary["errors"]<=3:summary.setdefault("error_samples",[]).append(str(e))
        return summary
