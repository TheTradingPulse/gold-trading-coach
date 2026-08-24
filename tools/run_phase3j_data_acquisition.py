"""Quote and acquire the fixed Phase 3J 2026 standard/micro OHLCV basket."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_data/v7/acquisition"
DATA = ROOT / "research_data/v7/forward_2026"
START = "2026-01-01T00:00:00Z"
END = "2026-08-23T19:00:00Z"
STANDARD = ("SI", "ES", "NQ", "YM", "RTY", "CL", "NG")
MICRO = ("MGC", "SIL", "MES", "MNQ", "MYM", "M2K", "MCL", "MNG")


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


def destination(group, symbol):
    return DATA / group / f"{symbol}_v_0_ohlcv_1m_20260101_20260823_1900Z.parquet"


def atomic_parquet(data, path):
    tmp = path.with_suffix(".partial.parquet")
    frame = data.to_df()
    if frame.empty:
        raise RuntimeError(f"Databento returned no rows for {path.stem}")
    frame.to_parquet(tmp)
    tmp.replace(path)
    return len(frame)


def main(approve_core=False, max_cost_usd=25.0):
    if max_cost_usd <= 0:
        raise SystemExit("Max cost must be positive")
    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    c = client()
    items = []

    for group, symbols in (("standard", STANDARD), ("micro", MICRO)):
        for symbol in symbols:
            path = destination(group, symbol)
            exists = path.exists() and path.stat().st_size > 0
            # The installed Databento SDK's metadata.get_cost method does not
            # accept stype_out. The historical download method does. Keep the
            # two parameter sets deliberately separate.
            cost = 0.0 if exists else float(c.metadata.get_cost(**quote_request(symbol)))
            items.append({
                "group": group,
                "symbol": symbol,
                "continuous_symbol": f"{symbol}.v.0",
                "destination": str(path),
                "already_present": exists,
                "quoted_cost_usd": cost,
                "downloaded_this_run": False,
            })
            state = "PRESENT" if exists else f"${cost:.4f}"
            print(f"{group.upper():8s} {symbol:4s}: {state}")

    total_cost = sum(item["quoted_cost_usd"] for item in items)
    quote = {
        "schema": "TP_PHASE3J_ACQUISITION_QUOTE_1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "period": {"start": START, "end_exclusive": END},
        "items": items,
        "total_missing_quoted_cost_usd": total_cost,
        "hard_cap_usd": max_cost_usd,
        "approved": bool(approve_core),
        "purchased": False,
    }
    (OUT / "phase3j_quote.json").write_text(json.dumps(quote, indent=2), encoding="utf-8")
    print(f"TOTAL MISSING QUOTED COST: ${total_cost:.4f}")
    print(f"HARD CAP: ${max_cost_usd:.2f}")

    if not approve_core:
        print("PURCHASE APPROVAL REQUIRED")
        return 3
    if total_cost > max_cost_usd:
        print("HARD CAP EXCEEDED; NOTHING PURCHASED")
        return 4

    completed = []
    for item in items:
        path = Path(item["destination"])
        if item["already_present"]:
            completed.append(item)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"DOWNLOADING {item['group'].upper()} {item['symbol']}...")
        rows = atomic_parquet(c.timeseries.get_range(**download_request(item["symbol"])), path)
        item["downloaded_this_run"] = True
        item["rows"] = rows
        item["size_bytes"] = path.stat().st_size
        completed.append(item)
        print(f"READY {item['symbol']}: {rows:,} rows")

    quote["purchased"] = True
    quote["completed_utc"] = datetime.now(timezone.utc).isoformat()
    (OUT / "phase3j_quote.json").write_text(json.dumps(quote, indent=2), encoding="utf-8")
    manifest = {
        "schema": "TP_PHASE3J_ACQUISITION_MANIFEST_1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "period": quote["period"],
        "quoted_cost_usd": total_cost,
        "items": completed,
        "integrity": "ok",
        "dashboard_modified": False,
        "canonical_research_modified": False,
    }
    (OUT / "phase3j_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"DATA ROOT: {DATA}")
    print("DASHBOARD/CANONICAL RESEARCH: untouched")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--approve-core", action="store_true")
    parser.add_argument("--max-cost-usd", type=float, default=25.0)
    args = parser.parse_args()
    raise SystemExit(main(args.approve_core, args.max_cost_usd))
