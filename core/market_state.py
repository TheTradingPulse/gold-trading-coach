"""
The Trading Pulse - Universal Market State

MarketState is the common contract between:

    Market Data
        -> Analysis Engines
        -> MarketState
        -> Dashboard
        -> Futures Professor
        -> Scanner
        -> Alerts / Telegram
        -> Future API

The dashboard and Professor should consume the SAME MarketState rather than
independently calculating market conditions.

No AI-generated trading values belong here. Values stored in MarketState
must come from deterministic Trading Pulse engines or validated statistics.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional
import json

try:
    from core.instruments import Instrument, get_instrument
except ImportError:
    from instruments import Instrument, get_instrument


VALID_SETUP_STATES = {
    "SCANNING",
    "WATCHING",
    "APPROACHING",
    "IN_ZONE",
    "CONFIRMING",
    "TRADE_READY",
    "ACTIVE",
    "COMPLETED",
    "STOPPED",
    "INVALIDATED",
}


@dataclass
class ZoneState:
    type: str
    lower_bound: float
    upper_bound: float

    timeframe: Optional[str] = None
    strength: Optional[float] = None
    freshness_score: Optional[float] = None
    retest_count: Optional[int] = None
    created_at: Optional[str] = None

    grade: Optional[str] = None
    distance_points: Optional[float] = None
    distance_percent: Optional[float] = None

    selected: bool = False
    actionable: bool = False

    def midpoint(self) -> float:
        return (self.lower_bound + self.upper_bound) / 2.0

    def contains(self, price: float) -> bool:
        return self.lower_bound <= price <= self.upper_bound


@dataclass
class ConfirmationState:
    price_in_zone: bool = False
    lower_timeframe_confirmed: bool = False
    structural_trigger: bool = False
    risk_validated: bool = False

    confirmation_timeframe: Optional[str] = None
    confirmation_reason: Optional[str] = None
    structural_reason: Optional[str] = None
    risk_reason: Optional[str] = None

    conditions_met: int = 0
    conditions_total: int = 4

    missing_conditions: list[str] = field(default_factory=list)


@dataclass
class TargetState:
    name: str
    price: float

    reward_points: Optional[float] = None
    reward_ticks: Optional[float] = None
    reward_dollars_per_contract: Optional[float] = None
    rr_ratio: Optional[float] = None


@dataclass
class TradeState:
    direction: str

    entry: float
    stop: float
    targets: list[TargetState] = field(default_factory=list)

    risk_points: Optional[float] = None
    risk_ticks: Optional[float] = None
    risk_dollars_per_contract: Optional[float] = None

    setup_grade: Optional[str] = None

    # Must eventually come from validated historical setup statistics.
    historical_probability: Optional[float] = None
    probability_sample_size: Optional[int] = None

    invalidation_reason: Optional[str] = None


@dataclass
class MarketState:
    # Instrument identity
    root_symbol: str
    instrument_name: str
    asset_class: str
    exchange: str
    currency: str

    # Contract identity
    contract_selection: str
    contract_symbol: Optional[str] = None
    data_symbol: Optional[str] = None

    # Market data
    current_price: Optional[float] = None
    market_timestamp: Optional[str] = None
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Analysis
    trends: dict[str, str] = field(default_factory=dict)
    market_bias: str = "neutral"
    alignment_score: float = 0.0

    # Zones
    supply_zones: list[ZoneState] = field(default_factory=list)
    demand_zones: list[ZoneState] = field(default_factory=list)
    selected_zone: Optional[ZoneState] = None

    # Setup
    setup_state: str = "SCANNING"
    setup_direction: Optional[str] = None
    confirmation: ConfirmationState = field(default_factory=ConfirmationState)

    # Confirmed trade - remains None until deterministic rules qualify it.
    trade: Optional[TradeState] = None

    # Context
    market_session: Optional[str] = None
    news_risk: Optional[str] = None

    # Professor / provenance bridge
    professor_context: dict[str, Any] = field(default_factory=dict)
    rule_references: list[dict[str, Any]] = field(default_factory=list)

    # Diagnostics
    warnings: list[str] = field(default_factory=list)
    engine_versions: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        self.root_symbol = self.root_symbol.upper()

        self.setup_state = self.setup_state.upper()

        if self.setup_state not in VALID_SETUP_STATES:
            raise ValueError(
                f"Invalid setup state '{self.setup_state}'. "
                f"Expected one of: {sorted(VALID_SETUP_STATES)}"
            )

        if self.setup_direction:
            self.setup_direction = self.setup_direction.upper()

        self.market_bias = self.market_bias.lower()

    @property
    def has_trade(self) -> bool:
        return self.trade is not None

    @property
    def is_actionable(self) -> bool:
        return self.setup_state in {"TRADE_READY", "ACTIVE"} and self.trade is not None

    @property
    def professor_ready(self) -> bool:
        """
        A MarketState is Professor-ready when it contains enough identity and
        market context to be serialized and explained.
        """
        return (
            bool(self.root_symbol)
            and self.current_price is not None
            and bool(self.trends)
        )

    def to_dict(self) -> dict:
        """Return a JSON-safe dictionary."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """
        Serialize the exact state consumed by the dashboard/Professor.
        """
        return json.dumps(
            self.to_dict(),
            indent=indent,
            default=str,
        )

    def professor_payload(self) -> dict:
        """
        Return the structured payload intended for the Futures Professor.

        The Professor may explain and compare this information, but should not
        replace deterministic engine calculations with invented trading values.
        """
        return {
            "instrument": {
                "root_symbol": self.root_symbol,
                "contract_symbol": self.contract_symbol,
                "data_symbol": self.data_symbol,
                "name": self.instrument_name,
                "exchange": self.exchange,
                "contract_selection": self.contract_selection,
            },
            "market": {
                "current_price": self.current_price,
                "market_timestamp": self.market_timestamp,
                "market_session": self.market_session,
                "bias": self.market_bias,
                "alignment_score": self.alignment_score,
                "trends": self.trends,
            },
            "setup": {
                "state": self.setup_state,
                "direction": self.setup_direction,
                "selected_zone": (
                    asdict(self.selected_zone)
                    if self.selected_zone is not None
                    else None
                ),
                "confirmation": asdict(self.confirmation),
                "trade": (
                    asdict(self.trade)
                    if self.trade is not None
                    else None
                ),
            },
            "knowledge_bridge": {
                "professor_context": self.professor_context,
                "rule_references": self.rule_references,
            },
            "warnings": self.warnings,
            "generated_at": self.generated_at,
        }


def create_empty_market_state(symbol: str = "GC") -> MarketState:
    """
    Create an empty MarketState from the futures instrument registry.

    Analysis engines populate this object later.
    """
    instrument: Instrument = get_instrument(symbol)

    return MarketState(
        root_symbol=instrument.root_symbol,
        instrument_name=instrument.name,
        asset_class=instrument.asset_class,
        exchange=instrument.exchange,
        currency=instrument.currency,
        contract_selection=instrument.contract_selection,
        data_symbol=instrument.data_symbol,
    )
