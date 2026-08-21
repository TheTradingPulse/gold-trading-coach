"""
The Trading Pulse - Futures Instrument Registry

Central source of truth for futures contract specifications.

GC remains the only enabled production instrument. The seven Market Watch
instruments are registered now so the UI and future multi-market architecture
share canonical identity, while enabled=False prevents them from being treated
as validated Trading Pulse analysis instruments before their storage/engines
are generalized.
"""

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass(frozen=True)
class Instrument:
    root_symbol: str
    name: str
    asset_class: str
    exchange: str
    currency: str
    tick_size: float
    tick_value: float
    point_value: float
    data_symbol: str
    micro_symbol: Optional[str] = None
    contract_selection: str = "front_month"
    enabled: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    def dollars_for_points(self, points: float, contracts: int = 1) -> float:
        return float(points) * self.point_value * int(contracts)

    def ticks_for_points(self, points: float) -> float:
        return 0.0 if self.tick_size <= 0 else float(points) / self.tick_size

    def dollars_for_ticks(self, ticks: float, contracts: int = 1) -> float:
        return float(ticks) * self.tick_value * int(contracts)


INSTRUMENTS = {
    "GC": Instrument("GC", "Gold Futures", "futures", "COMEX", "USD",
                     0.10, 10.00, 100.00, "GC=F", "MGC", enabled=True),
    "SI": Instrument("SI", "Silver Futures", "futures", "COMEX", "USD",
                     0.005, 25.00, 5000.00, "SI=F", "SIL", enabled=False),
    "ES": Instrument("ES", "E-mini S&P 500", "futures", "CME", "USD",
                     0.25, 12.50, 50.00, "ES=F", "MES", enabled=False),
    "NQ": Instrument("NQ", "E-mini Nasdaq 100", "futures", "CME", "USD",
                     0.25, 5.00, 20.00, "NQ=F", "MNQ", enabled=False),
    "YM": Instrument("YM", "E-mini Dow", "futures", "CBOT", "USD",
                     1.00, 5.00, 5.00, "YM=F", "MYM", enabled=False),
    "RTY": Instrument("RTY", "E-mini Russell 2000", "futures", "CME", "USD",
                      0.10, 5.00, 50.00, "RTY=F", "M2K", enabled=False),
    "CL": Instrument("CL", "WTI Crude Oil Futures", "futures", "NYMEX", "USD",
                     0.01, 10.00, 1000.00, "CL=F", "MCL", enabled=False),
    "NG": Instrument("NG", "Natural Gas Futures", "futures", "NYMEX", "USD",
                     0.001, 10.00, 10000.00, "NG=F", "MNG", enabled=False),
}


def get_instrument(symbol: str = "GC") -> Instrument:
    root = str(symbol).strip().upper()
    if root not in INSTRUMENTS:
        available = ", ".join(sorted(INSTRUMENTS.keys()))
        raise KeyError(f"Instrument '{root}' is not registered. Available instruments: {available}")
    return INSTRUMENTS[root]


def list_instruments(enabled_only: bool = True) -> list[Instrument]:
    instruments = list(INSTRUMENTS.values())
    return [i for i in instruments if i.enabled] if enabled_only else instruments


def instrument_exists(symbol: str) -> bool:
    return str(symbol).strip().upper() in INSTRUMENTS


def get_enabled_symbols() -> list[str]:
    return [i.root_symbol for i in list_instruments(enabled_only=True)]
