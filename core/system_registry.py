"""Read-only access to the TradingPulse canonical system registry."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config" / "tradingpulse_registry.json"


@lru_cache(maxsize=1)
def load_registry() -> dict[str, Any]:
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if data.get("schema") != "TP_CANONICAL_SYSTEM_REGISTRY_1":
        raise RuntimeError("Unsupported TradingPulse system registry schema")
    return data


def production_entrypoint() -> Path:
    return ROOT / load_registry()["production"]["entrypoint"]


def research_path(name: str) -> Path:
    value = load_registry()["research"].get(name)
    if not value:
        raise KeyError(name)
    return ROOT / value


def live_evidence_enabled() -> bool:
    state = load_registry()["production"].get("elite_state")
    return state not in {None, "FAIL_CLOSED_UNTIL_CANONICAL_EVIDENCE_ADAPTER"}
