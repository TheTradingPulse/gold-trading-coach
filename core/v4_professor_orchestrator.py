from __future__ import annotations
from v4_point_in_time import PointInTimeReader
from v4_chart_intelligence import build_chart_packet
from v4_professor_chart_analyst import build_professor_prompt
from v4_backtest_evidence import EvidenceStore
from v4_learning_loop import LearningStore

class ProfessorOrchestrator:
    def __init__(self,warehouse="research_data/v4/market_warehouse.db",
                 evidence="research_data/v4/evidence.db",learning="research_data/v4/professor_learning.db"):
        self.reader=PointInTimeReader(warehouse); self.evidence=EvidenceStore(evidence); self.learning=LearningStore(learning)
    def prepare(self,question,symbol,as_of,timeframes=("5m","15m","1H","4H","D"),
                market_state_payload=None,selected_setup=None):
        frames=self.reader.multi_timeframe(symbol,as_of,timeframes)
        packet=build_chart_packet(symbol,frames,market_state_payload,selected_setup,as_of)
        evidence=self.evidence.summary(symbol=symbol)
        prompt=build_professor_prompt(question,packet,evidence)
        qa_id=self.learning.log_qa(question,symbol=symbol,grounding={"as_of":str(as_of),"timeframes":list(timeframes)})
        return {"qa_id":qa_id,"prompt":prompt,"chart_packet":packet,"evidence":evidence}
