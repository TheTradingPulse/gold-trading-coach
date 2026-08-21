"""
Trading Pulse V2.9E - deterministic trade-management plan.

Creates management instructions from an authorized canonical plan. It does not
send orders. Rules are intentionally explicit and serializable for replay.
"""
from dataclasses import dataclass, asdict
from typing import Any

@dataclass(frozen=True)
class ManagementPlan:
    active: bool
    contracts: int
    targets: tuple
    move_stop_to_breakeven_after: str | None
    cancel_if: tuple
    notes: tuple
    def to_dict(self):
        d=asdict(self); d["targets"]=list(self.targets); d["cancel_if"]=list(self.cancel_if); d["notes"]=list(self.notes); return d

def build_management_plan(execution: Any, authorization: Any) -> ManagementPlan:
    if not getattr(execution,"trade_ready",False) or not getattr(authorization,"approved",False):
        return ManagementPlan(False,0,(),None,("Trade loses canonical TRADE_READY status before entry.",),("No management orders are active.",))
    targets=tuple(float(x) for x in getattr(execution,"targets",()) or ())
    contracts=int(getattr(authorization,"contracts",0))
    if not targets:
        return ManagementPlan(False,0,(),None,("No structural target exists.",),("Trade management rejected.",))
    # Conservative default: management metadata only. Allocation/order mechanics
    # belong to the eventual broker adapter.
    return ManagementPlan(
        True, contracts, targets,
        "T1_FILLED" if len(targets) > 1 else None,
        ("Setup invalidates before entry.","Canonical risk authorization is revoked."),
        ("Targets remain structural.","No trailing stop is invented by the UI.","Broker adapter must confirm fills before state transitions.")
    )
