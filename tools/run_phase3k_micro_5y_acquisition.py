"""Controlled five-year micro OHLCV acquisition for Trading Pulse."""
from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_data/v7/acquisition"
DATA = ROOT / "research_data/v7/micro_5y"
START = "2021-01-01T00:00:00Z"
END = "2026-01-01T00:00:00Z"
MICROS = ("MGC", "SIL", "MES", "MNQ", "MYM", "M2K", "MCL", "MNG")
MIN_FREE_BYTES = 2 * 1024**3


def client():
    try:
        import databento as db
    except ImportError:
        raise SystemExit("databento package missing from .venv")
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        raise SystemExit("DATABENTO_API_KEY is not set in this PowerShell window")
    return db.Historical(key)


def quote_request(symbol):
    return {
        "dataset": "GLBX.MDP3",
        "schema": "ohlcv-1m",
        "symbols": f"{symbol}.v.0",
        "stype_in": "continuous",
        "start": START,
        "end": END,
    }


def download_request(symbol):
    params = quote_request(symbol)
    params["stype_out"] = "instrument_id"
    return params


def destination(symbol):
    return DATA / f"{symbol}_v_0_ohlcv_1m_20210101_20260101.parquet"


def atomic_parquet(data, path):
    temporary = path.with_suffix(".partial.parquet")
    frame = data.to_df()
    if frame.empty:
        raise RuntimeError(f"Databento returned no rows for {path.stem}")
    frame.to_parquet(temporary)
    temporary.replace(path)
    return len(frame)


def main(approve_purchase=False, max_cost_usd=45.0):
    if max_cost_usd <= 0:
        raise SystemExit("Max cost must be positive")
    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)

    free_bytes = shutil.disk_usage(DATA).free
    if free_bytes < MIN_FREE_BYTES:
        print(f"INSUFFICIENT FREE SPACE: {free_bytes / 1024**3:.2f} GB; 2 GB required")
        return 5

    c = client()
    items = []
    for symbol in MICROS:
        path = destination(symbol)
        present = path.exists() and path.stat().st_size > 0
        cost = 0.0 if present else float(c.metadata.get_cost(**quote_request(symbol)))
        item = {
            "symbol": symbol,
            "continuous_symbol": f"{symbol}.v.0",
            "destination": str(path),
            "already_present": present,
            "quoted_cost_usd": cost,
            "downloaded_this_run": False,
        }
        items.append(item)
        print(f"{symbol:4s}: {'PRESENT' if present else f'${cost:.4f}'}")

    total_cost = sum(item["quoted_cost_usd"] for item in items)
    quote = {
        "schema": "TP_PHASE3K_MICRO_5Y_PURCHASE_QUOTE_1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "period": {"start": START, "end_exclusive": END},
        "items": items,
        "total_missing_quoted_cost_usd": total_cost,
        "hard_cap_usd": max_cost_usd,
        "approved": bool(approve_purchase),
        "purchased": False,
    }
    quote_path = OUT / "phase3k_micro_5y_purchase_quote.json"
    quote_path.write_text(json.dumps(quote, indent=2), encoding="utf-8")
    print(f"TOTAL MISSING QUOTED COST: ${total_cost:.4f}")
    print(f"HARD CAP: ${max_cost_usd:.2f}")

    if not approve_purchase:
        print("PURCHASE APPROVAL REQUIRED")
        return 3
    if total_cost > max_cost_usd:
        print("HARD CAP EXCEEDED; NOTHING PURCHASED")
        return 4

    for item in items:
        if item["already_present"]:
            continue
        path = Path(item["destination"])
        print(f"DOWNLOADING {item['symbol']} 2021-2025...")
        rows = atomic_parquet(c.timeseries.get_range(**download_request(item["symbol"])), path)
        item["downloaded_this_run"] = True
        item["rows"] = rows
        item["size_bytes"] = path.stat().st_size
        print(f"READY {item['symbol']}: {rows:,} rows")

    quote["purchased"] = True
    quote["completed_utc"] = datetime.now(timezone.utc).isoformat()
    quote_path.write_text(json.dumps(quote, indent=2), encoding="utf-8")
    manifest = {
        "schema": "TP_PHASE3K_MICRO_5Y_MANIFEST_1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "period": quote["period"],
        "quoted_cost_usd": total_cost,
        "items": items,
        "integrity": "ok",
        "dashboard_modified": False,
        "canonical_research_modified": False,
    }
    (OUT / "phase3k_micro_5y_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"DATA ROOT: {DATA}")
    print("DASHBOARD/CANONICAL RESEARCH: untouched")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--approve-purchase", action="store_true")
    parser.add_argument("--max-cost-usd", type=float, default=45.0)
    args = parser.parse_args()
    raise SystemExit(main(args.approve_purchase, args.max_cost_usd))
