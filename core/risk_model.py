"""Trading Pulse V3.1E - canonical structural risk model.

One deterministic stop-buffer policy shared by setup previews and executable
trade plans. The zone edge remains the structural invalidation boundary; this
module only determines how far beyond that boundary the stop sits.

This is a production heuristic pending historical calibration. It intentionally
uses zone width + instrument ticks rather than pretending one universal number
of ticks is appropriate across every futures market/timeframe.
"""
from __future__ import annotations
from dataclasses import dataclass

ENGINE_VERSION = "3.1E"

# Minimum noise allowance by timeframe. Wider/slower structures receive more
# breathing room, but zone-relative padding prevents tick size alone from
# controlling risk across unrelated contracts.
MIN_BUFFER_TICKS = {
    "1m": 3,
    "5m": 4,
    "15m": 5,
    "1H": 6,
    "4H": 8,
    "D": 10,
    "W": 12,
    "M": 12,
}
ZONE_BUFFER_FRACTION = {
    "1m": 0.08,
    "5m": 0.10,
    "15m": 0.12,
    "1H": 0.15,
    "4H": 0.18,
    "D": 0.20,
    "W": 0.20,
    "M": 0.20,
}
MAX_ZONE_BUFFER_FRACTION = 0.25

@dataclass(frozen=True)
class StructuralRisk:
    stop: float
    buffer_points: float
    buffer_ticks: float
    zone_width_points: float
    risk_points: float
    risk_ticks: float
    risk_dollars_per_contract: float
    model: str = "zone_relative_structural_v1"


def structural_stop(instrument, direction: str, entry: float, lower: float, upper: float, timeframe: str) -> StructuralRisk:
    tick = float(instrument.tick_size)
    if tick <= 0:
        raise ValueError("Instrument tick size must be positive.")
    lower, upper, entry = float(lower), float(upper), float(entry)
    if upper <= lower:
        raise ValueError("Execution zone must have positive width.")
    tf = str(timeframe or "15m")
    width = upper - lower
    floor = tick * int(MIN_BUFFER_TICKS.get(tf, 5))
    proportional = width * float(ZONE_BUFFER_FRACTION.get(tf, 0.12))
    ceiling = max(floor, width * MAX_ZONE_BUFFER_FRACTION)
    buffer_points = min(max(floor, proportional), ceiling)
    # Snap outward to a whole tick so the stop is always contract-valid.
    import math
    buffer_ticks = max(1, math.ceil(buffer_points / tick - 1e-12))
    buffer_points = buffer_ticks * tick
    d = str(direction).upper()
    if d == "LONG":
        stop = lower - buffer_points
        risk = entry - stop
    elif d == "SHORT":
        stop = upper + buffer_points
        risk = stop - entry
    else:
        raise ValueError(f"Unsupported direction: {direction}")
    if risk <= 0:
        raise ValueError("Structural stop does not create positive risk distance.")
    return StructuralRisk(
        stop=stop,
        buffer_points=buffer_points,
        buffer_ticks=buffer_ticks,
        zone_width_points=width,
        risk_points=risk,
        risk_ticks=risk/tick,
        risk_dollars_per_contract=instrument.dollars_for_points(risk),
    )
