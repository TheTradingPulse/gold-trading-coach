"""
The Trading Pulse - Futures Instrument Registry

Central source of truth for futures contract specifications.

Gold (GC) is the first production instrument. Additional futures markets
will be registered here as they are validated.

IMPORTANT:
- Trading logic should reference Instrument objects rather than hard-coded
  Gold-specific contract values.
- Contract-specific symbols are resolved separately.
- This file contains contract specifications, not trading signals.
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
        """Convert a price move in points into contract P/L."""
        return float(points) * self.point_value * int(contracts)

    def ticks_for_points(self, points: float) -> float:
        """Convert a price move into ticks."""
        if self.tick_size <= 0:
            return 0.0
        return float(points) / self.tick_size

    def dollars_for_ticks(self, ticks: float, contracts: int = 1) -> float:
        """Convert ticks into contract P/L."""
        return float(ticks) * self.tick_value * int(contracts)


# ---------------------------------------------------------------------
# Instrument Registry
# ---------------------------------------------------------------------
#
# GC is intentionally the only enabled production instrument right now.
# Other futures will be added after the GC pipeline is validated.
#
# data_symbol currently points to the existing Yahoo continuous/front-month
# data feed used by Trading Pulse. A future Contract Resolver will replace
# this with an explicit active-contract mapping when supported by the
# production market-data provider.
# ---------------------------------------------------------------------

INSTRUMENTS = {
    "GC": Instrument(
        root_symbol="GC",
        name="Gold Futures",
        asset_class="futures",
        exchange="COMEX",
        currency="USD",
        tick_size=0.10,
        tick_value=10.00,
        point_value=100.00,
        data_symbol="GC=F",
        micro_symbol="MGC",
        contract_selection="front_month",
        enabled=True,
    ),
}


def get_instrument(symbol: str = "GC") -> Instrument:
    """
    Return an instrument from the registry.

    Accepts root symbols case-insensitively.
    """
    root = str(symbol).strip().upper()

    if root not in INSTRUMENTS:
        available = ", ".join(sorted(INSTRUMENTS.keys()))
        raise KeyError(
            f"Instrument '{root}' is not registered. "
            f"Available instruments: {available}"
        )

    return INSTRUMENTS[root]


def list_instruments(enabled_only: bool = True) -> list[Instrument]:
    """Return registered futures instruments."""
    instruments = list(INSTRUMENTS.values())

    if enabled_only:
        instruments = [instrument for instrument in instruments if instrument.enabled]

    return instruments


def instrument_exists(symbol: str) -> bool:
    """Return True when a root symbol exists in the registry."""
    return str(symbol).strip().upper() in INSTRUMENTS


def get_enabled_symbols() -> list[str]:
    """Return enabled root symbols for the future market scanner."""
    return [
        instrument.root_symbol
        for instrument in list_instruments(enabled_only=True)
    ]
