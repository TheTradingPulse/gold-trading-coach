"""Read-only Databento quote for the five-year Trading Pulse micro basket."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_data/v7/acquisition"
START = "2021-01-01T00:00:00Z"
END = "2026-01-01T00:00:00Z"
MICROS = ("MGC", "SIL", "MES", "MNQ", "MYM", "M2K", "MCL", "MNG")


def quote_request(symbol):
    return {
        "dataset": "GLBX.MDP3",
        "schema": "ohlcv-1m",
        "symbols": f"{symbol}.v.0",
        "stype_in": "continuous",
        "start": START,
        "end": END,
    }


def client():
    try:
        import databento as db
    except ImportError:
        raise SystemExit("databento package missing from .venv")
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        raise SystemExit("DATABENTO_API_KEY is not set in this PowerShell window")
    return db.Historical(key)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    c = client()
    items = []
    for symbol in MICROS:
        cost = float(c.metadata.get_cost(**quote_request(symbol)))
        items.append({
            "symbol": symbol,
            "continuous_symbol": f"{symbol}.v.0",
            "quoted_cost_usd": cost,
        })
        print(f"{symbol:4s}: ${cost:.4f}")

    total = sum(item["quoted_cost_usd"] for item in items)
    report = {
        "schema": "TP_PHASE3K_MICRO_5Y_QUOTE_1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": "GLBX.MDP3",
        "data_schema": "ohlcv-1m",
        "period": {"start": START, "end_exclusive": END},
        "items": items,
        "combined_quoted_cost_usd": total,
        "purchased": False,
        "download_capability_present": False,
    }
    path = OUT / "phase3k_micro_5y_quote.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"TOTAL FIVE-YEAR MICRO QUOTE: ${total:.4f}")
    print(f"QUOTE READY: {path}")
    print("NO DATA PURCHASED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
