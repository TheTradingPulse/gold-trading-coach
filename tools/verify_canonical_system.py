from __future__ import annotations

import json
import py_compile
from pathlib import Path

ROOT = Path(r"C:\TradingPulse")
registry = json.loads((ROOT / "config" / "tradingpulse_registry.json").read_text(encoding="utf-8"))
required = [
    registry["production"]["entrypoint"],
    registry["production"]["market_state"],
    registry["production"]["structure_detector"],
    registry["production"]["trade_plan"],
    registry["production"]["execution_lifecycle"],
    registry["research"]["canonical_multitimeframe_warehouse"],
    registry["research"]["professional_zone_reference"],
]
missing = [p for p in required if not (ROOT / p).exists()]
for p in [ROOT / "dashboard.py", ROOT / "core" / "system_registry.py"]:
    py_compile.compile(str(p), doraise=True)
print("Trading Pulse Canonical Verification")
print(f"Registry: {registry['schema']}")
print(f"Live evidence: {registry['production']['elite_state']}")
print(f"Required paths missing: {len(missing)}")
for p in missing: print(f"  MISSING: {p}")
if missing: raise SystemExit(2)
print("VERIFICATION: ok")
