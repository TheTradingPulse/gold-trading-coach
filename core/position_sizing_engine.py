"""
Trading Pulse V2.9D - deterministic account risk / position sizing.

This module sizes only an already-canonical TRADE_READY plan.
It does not place orders and it never increases risk to force a trade.
"""
from dataclasses import dataclass, asdict
from typing import Optional, Any
import math

@dataclass(frozen=True)
class RiskAuthorization:
    approved: bool
    contracts: int
    allowed_risk_dollars: float
    actual_risk_dollars: float
    risk_per_contract: float
    reason: str
    def to_dict(self): return asdict(self)

def authorize_position(
    execution: Any,
    account_balance: float,
    max_risk_percent: float = 0.25,
    max_risk_dollars: Optional[float] = None,
    max_contracts: int = 10,
) -> RiskAuthorization:
    if not getattr(execution, "broker_eligible", False):
        return RiskAuthorization(False,0,0.0,0.0,0.0,"Execution is not broker eligible.")
    if account_balance <= 0 or max_risk_percent <= 0 or max_contracts < 1:
        return RiskAuthorization(False,0,0.0,0.0,0.0,"Invalid account risk configuration.")
    pct_budget = account_balance * (max_risk_percent / 100.0)
    budget = pct_budget if max_risk_dollars is None else min(pct_budget, float(max_risk_dollars))
    rpc = float(getattr(execution, "risk_dollars_per_contract", 0.0) or 0.0)
    if rpc <= 0:
        return RiskAuthorization(False,0,budget,0.0,rpc,"Risk per contract is unavailable.")
    contracts = min(max_contracts, math.floor(budget / rpc))
    if contracts < 1:
        return RiskAuthorization(False,0,budget,0.0,rpc,"One contract exceeds the configured risk budget.")
    actual = contracts * rpc
    return RiskAuthorization(True,contracts,budget,actual,rpc,"Position fits the configured account risk budget.")
