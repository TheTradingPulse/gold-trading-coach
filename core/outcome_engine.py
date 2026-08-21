"""The Trading Pulse - Historical Outcome Engine V2.8D.

Future candles are used ONLY after a frozen historical decision exists.
They never participate in generating the setup fingerprint.
"""
from dataclasses import dataclass, asdict
from typing import Optional
import pandas as pd

@dataclass
class OutcomeResult:
    status: str
    entry: float
    stop: float
    target: float
    direction: str
    resolved_at: Optional[str] = None
    bars_to_resolution: Optional[int] = None
    realized_r: Optional[float] = None
    mfe_r: float = 0.0
    mae_r: float = 0.0
    ambiguous_bar: bool = False
    reason: str = ""
    def to_dict(self): return asdict(self)

def evaluate_trade_outcome(fingerprint: dict, future_df: pd.DataFrame, *, conservative_same_bar=True) -> OutcomeResult:
    t=fingerprint.get("trade",{}) or {}
    direction=(t.get("direction") or fingerprint.get("confirmation",{}).get("setup_direction") or "").upper()
    entry,stop,target=t.get("entry"),t.get("stop"),t.get("target_price")
    if direction not in {"LONG","SHORT"} or None in {entry,stop,target}:
        return OutcomeResult("NOT_EVALUABLE", entry or 0, stop or 0, target or 0, direction, reason="Frozen fingerprint has no complete trade plan.")
    entry,stop,target=map(float,(entry,stop,target)); risk=abs(entry-stop)
    if risk<=0: return OutcomeResult("NOT_EVALUABLE",entry,stop,target,direction,reason="Invalid zero risk.")
    if future_df is None or future_df.empty:
        return OutcomeResult("UNRESOLVED",entry,stop,target,direction,reason="No future candles supplied.")
    df=future_df.sort_index().copy(); mfe=mae=0.0
    for n,(ts,row) in enumerate(df.iterrows(),1):
        hi,lo=float(row.high),float(row.low)
        if direction=="LONG":
            mfe=max(mfe,(hi-entry)/risk); mae=max(mae,(entry-lo)/risk)
            hit_stop=lo<=stop; hit_target=hi>=target
        else:
            mfe=max(mfe,(entry-lo)/risk); mae=max(mae,(hi-entry)/risk)
            hit_stop=hi>=stop; hit_target=lo<=target
        if hit_stop and hit_target:
            status="LOSS" if conservative_same_bar else "AMBIGUOUS"
            rr=-1.0 if conservative_same_bar else None
            return OutcomeResult(status,entry,stop,target,direction,str(ts),n,rr,round(mfe,4),round(mae,4),True,"Stop and target touched in same candle; conservative ordering applied." if conservative_same_bar else "Intrabar order unknowable.")
        if hit_stop:
            return OutcomeResult("LOSS",entry,stop,target,direction,str(ts),n,-1.0,round(mfe,4),round(mae,4),False,"Stop touched before target.")
        if hit_target:
            rr=abs(target-entry)/risk
            return OutcomeResult("WIN",entry,stop,target,direction,str(ts),n,round(rr,4),round(mfe,4),round(mae,4),False,"Target touched before stop.")
    return OutcomeResult("UNRESOLVED",entry,stop,target,direction,None,len(df),None,round(mfe,4),round(mae,4),False,"Neither stop nor target resolved inside evaluation horizon.")
