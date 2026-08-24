from __future__ import annotations
from v4_contextual_features import build
from v4_contextual_similarity import nearest_scored,stats,weighted_stats
from v4_context_evidence import load
from v4_grandslam_policy import decide_grandslam

class ContextualIntelligence:
    def __init__(self,evidence="research_data/v4/context_evidence_v4.db"):
        self.rows=load(evidence)
    def analyze(self,candidate,state=None,frames=None,as_of=None):
        f=build(candidate,state,frames,as_of)
        scored=nearest_scored(self.rows,f,limit=750,minimum=.68)
        rows=[r for _,r in scored]; s=stats(rows); ws=weighted_stats(scored)
        s.update({k:v for k,v in ws.items() if k.startswith('weighted_') or k=='mean_similarity'})
        d=decide_grandslam(s,completeness=f.get('feature_completeness',0),mean_similarity=s.get('mean_similarity',0),
          projected_rr=f.get('projected_rr'),actionable=f.get('is_actionable'))
        return {"schema":"tradingpulse.contextual_intelligence.v2","features":f,"comparables":len(rows),"evidence":s,"decision":d,
          "research_only":True,"live_policy_untouched":True}

def professor_evidence(packet):
    e=packet.get('evidence',{});d=packet.get('decision',{});f=packet.get('features',{})
    return {"research_tier":d.get('tier'),"preferred_target":d.get('preferred_target'),"triggered_comparables":e.get('triggered'),
      "historical_3r_hit_pct":e.get('hit_3r_pct'),"historical_5r_hit_pct":e.get('hit_5r_pct'),"weighted_3r_hit_pct":e.get('weighted_3r_pct'),
      "weighted_5r_hit_pct":e.get('weighted_5r_pct'),"mean_similarity":e.get('mean_similarity'),"avg_mfe_r":e.get('avg_mfe_r'),
      "avg_mae_r":e.get('avg_mae_r'),"context":f,"feature_completeness":f.get('feature_completeness'),"research_only":True}
