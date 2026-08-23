from __future__ import annotations
from v4_sniper_features import extract
from v4_context_similarity import nearest,evidence
from v4_sniper_policy import decide

class SniperEngine:
    def __init__(self, historical_rows):
        self.rows=historical_rows
    def analyze(self,candidate,state=None):
        f=extract(candidate,state)
        comps=nearest(self.rows,f)
        stats=evidence(comps)
        d=decide(stats,completeness=f["feature_completeness"])
        return {"features":f,"comparables":len(comps),"evidence":stats,
                "decision":d,"research_only":True}
