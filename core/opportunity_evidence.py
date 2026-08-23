"""V3.4D read/write-neutral evidence schema helpers. No database writes occur here."""
from __future__ import annotations
from dataclasses import dataclass,asdict
from typing import Any
@dataclass(frozen=True)
class OpportunityEvidence:
    symbol:str; candidate_id:str; tier:str; timestamp:str|None; timeframe:str; direction:str
    setup_score:float; composite_score:float; lifecycle:str; zone_quality:float; freshness:float
    retests:int; projected_rr:float|None; mtf_aligned:int; mtf_total:int; confirmations:int
    def to_dict(self): return asdict(self)
def from_opportunity(o:Any,timestamp=None):
    c=o.candidate
    return OpportunityEvidence(o.symbol,str(c.candidate_id),str(o.tier),None if timestamp is None else str(timestamp),str(c.timeframe),str(o.direction),float(c.setup_score),float(o.composite_score),str(c.lifecycle),float(c.zone_quality_score),float(c.freshness_score),int(c.retest_count),None if c.projected_rr is None else float(c.projected_rr),int(o.mtf_aligned),int(o.mtf_total),int(o.confirmation_count))
