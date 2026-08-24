from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import pandas as pd

KNOWN_DEGRADED = {"2025-11-28": "Databento reduced-quality day"}

@dataclass
class QualityFlag:
    symbol: str
    date: str
    severity: str
    reason: str
    source: str = "databento"

class HistoricalQualityRegistry:
    def __init__(self):
        self.flags = []

    def add(self, symbol, date, severity, reason, source="databento"):
        self.flags.append(QualityFlag(symbol, date, severity, reason, source))

    def seed_known(self, symbols):
        for day, reason in KNOWN_DEGRADED.items():
            for symbol in symbols:
                self.add(symbol, day, "degraded", reason)

    def is_flagged(self, symbol, ts):
        day = pd.Timestamp(ts).strftime("%Y-%m-%d")
        return any(f.symbol == symbol and f.date == day for f in self.flags)

    def to_dict(self):
        return [asdict(x) for x in self.flags]

    def save(self, path):
        p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
