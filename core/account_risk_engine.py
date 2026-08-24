"""Account-aware futures sizing and execution-feasibility policy."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import floor
from typing import Literal

ENGINE_VERSION = "TP_ACCOUNT_RISK_ENGINE_1"


@dataclass(frozen=True)
class ContractSpec:
    root: str
    standard: str
    micro: str
    standard_tick_value: float
    micro_tick_value: float
    standard_round_trip: float
    micro_round_trip: float
    micro_equivalence: float = 0.1


SPECS = {
    "GC": ContractSpec("GC", "GC", "MGC", 10, 1, 5.0, 1.5),
    "SI": ContractSpec("SI", "SI", "SIL", 25, 5, 5.0, 1.5, 0.2),
    "ES": ContractSpec("ES", "ES", "MES", 12.5, 1.25, 4.5, 1.5),
    "NQ": ContractSpec("NQ", "NQ", "MNQ", 5, .5, 4.5, 1.5),
    "YM": ContractSpec("YM", "YM", "MYM", 5, .5, 4.5, 1.5),
    "RTY": ContractSpec("RTY", "RTY", "M2K", 5, .5, 4.5, 1.5),
    "CL": ContractSpec("CL", "CL", "MCL", 10, 1, 5.0, 1.5),
    "NG": ContractSpec("NG", "NG", "MNG", 10, 1, 5.0, 1.5),
}


@dataclass(frozen=True)
class AccountProfile:
    name: str = "Apex 50K EOD PA Level 1"
    nominal_balance: float = 50_000
    current_balance: float = 50_000
    liquidation_threshold: float = 48_000
    daily_loss_remaining: float | None = 1_000
    max_standard_equivalents: float = 2
    risk_basis: Literal["drawdown", "nominal", "personal"] = "drawdown"
    personal_bankroll: float | None = None
    risk_percent: float = 2.0
    daily_risk_cap_percent: float = 20.0
    max_execution_cost_percent: float = 10.0
    preference: Literal["automatic", "standard", "micro"] = "automatic"
    slippage_ticks_each_side: float = 1.0

    @property
    def remaining_drawdown(self) -> float:
        return max(0.0, self.current_balance - self.liquidation_threshold)

    @property
    def risk_capital(self) -> float:
        if self.risk_basis == "nominal":
            return self.nominal_balance
        if self.risk_basis == "personal":
            return max(0.0, float(self.personal_bankroll or 0))
        return self.remaining_drawdown

    @property
    def risk_budget(self) -> float:
        budget = self.risk_capital * self.risk_percent / 100
        if self.daily_loss_remaining is not None:
            budget = min(budget, self.daily_loss_remaining * self.daily_risk_cap_percent / 100)
        return max(0.0, budget)


@dataclass(frozen=True)
class SizingDecision:
    engine_version: str
    eligible: bool
    status: str
    contract: str | None
    contract_type: str | None
    quantity: int
    risk_budget: float
    structural_risk_each: float
    execution_cost_each: float
    total_risk_each: float
    total_position_risk: float
    risk_percent_of_drawdown: float
    execution_cost_percent: float
    minimum_bankroll_1pct: float
    minimum_bankroll_2pct: float
    minimum_bankroll_3pct: float
    standard_quantity_if_eligible: int
    micro_quantity_if_eligible: int
    reason: str

    def to_dict(self):
        return asdict(self)


def _economics(spec: ContractSpec, kind: str, risk_ticks: float, slip: float):
    if kind == "standard":
        tick, fee, equiv, symbol = spec.standard_tick_value, spec.standard_round_trip, 1.0, spec.standard
    else:
        tick, fee, equiv, symbol = spec.micro_tick_value, spec.micro_round_trip, spec.micro_equivalence, spec.micro
    structural = risk_ticks * tick
    cost = fee + 2 * slip * tick
    return symbol, structural, cost, structural + cost, equiv


def size_trade(symbol: str, risk_ticks: float, profile: AccountProfile) -> dict:
    root = symbol.upper()
    if root not in SPECS:
        raise ValueError(f"unsupported futures root: {root}")
    if risk_ticks <= 0:
        raise ValueError("risk_ticks must be positive")
    spec, budget = SPECS[root], profile.risk_budget
    options = []
    for kind in ("standard", "micro"):
        contract, structural, cost, total, equiv = _economics(spec, kind, risk_ticks, profile.slippage_ticks_each_side)
        cost_pct = 100 * cost / structural if structural else float("inf")
        by_budget = floor(budget / total) if total else 0
        by_limit = floor(profile.max_standard_equivalents / equiv)
        qty = max(0, min(by_budget, by_limit)) if cost_pct <= profile.max_execution_cost_percent else 0
        options.append({"kind":kind,"contract":contract,"structural":structural,"cost":cost,"total":total,
                        "equiv":equiv,"cost_pct":cost_pct,"qty":qty})
    standard, micro = options
    if profile.preference == "standard":
        selected = standard
    elif profile.preference == "micro":
        selected = micro
    else:
        selected = standard if standard["qty"] >= 1 else micro
    qty = selected["qty"]
    if budget <= 0:
        status, reason = "NO_RISK_CAPITAL", "No usable drawdown or bankroll remains."
    elif selected["cost_pct"] > profile.max_execution_cost_percent:
        status, reason = "EXECUTION_COST_TOO_HIGH", "Estimated execution cost exceeds the configured percentage of structural risk."
    elif qty < 1:
        status, reason = "NO_EXECUTABLE_SIZE", "Even one permitted contract exceeds the risk budget or account limit."
    else:
        status = "STANDARD_ELIGIBLE" if selected["kind"] == "standard" else "MICRO_ONLY"
        reason = "Position fits risk, execution-cost, daily-loss, and contract-equivalence limits."
    total_risk = qty * selected["total"]
    dd = profile.remaining_drawdown
    return SizingDecision(ENGINE_VERSION, qty >= 1, status, selected["contract"] if qty else None,
        selected["kind"] if qty else None, qty, budget, selected["structural"], selected["cost"], selected["total"],
        total_risk, 100*total_risk/dd if dd else 0.0, selected["cost_pct"],
        selected["total"]/.01, selected["total"]/.02, selected["total"]/.03,
        standard["qty"], micro["qty"], reason).to_dict()
