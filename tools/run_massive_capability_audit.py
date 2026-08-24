from __future__ import annotations

import csv
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://api.massive.com"
SCHEMA = "TP_MASSIVE_CAPABILITY_AUDIT_1"


CHECKS = [
    {
        "name": "stocks_reference",
        "market": "stocks",
        "path": "/v3/reference/tickers",
        "params": {"market": "stocks", "active": "true", "limit": 1},
        "purpose": "Symbol and exchange reference data",
    },
    {
        "name": "stocks_previous_bar",
        "market": "stocks",
        "path": "/v2/aggs/ticker/SPY/prev",
        "params": {"adjusted": "true"},
        "purpose": "SPY context and historical aggregate access",
    },
    {
        "name": "stocks_snapshot",
        "market": "stocks",
        "path": "/v2/snapshot/locale/us/markets/stocks/tickers/SPY",
        "params": {},
        "purpose": "Current or delayed equity context",
    },
    {
        "name": "options_reference",
        "market": "options",
        "path": "/v3/reference/options/contracts",
        "params": {"underlying_ticker": "SPY", "limit": 1},
        "purpose": "Options-chain reference availability",
    },
    {
        "name": "futures_exchanges",
        "market": "futures",
        "path": "/futures/v1/exchanges",
        "params": {"limit": 1},
        "purpose": "Futures reference access",
    },
    {
        "name": "futures_products_es",
        "market": "futures",
        "path": "/futures/v1/products",
        "params": {"product_code": "ES", "limit": 1},
        "purpose": "ES product specification access",
    },
    {
        "name": "futures_contracts_es",
        "market": "futures",
        "path": "/futures/v1/contracts",
        "params": {"product_code": "ES", "limit": 1},
        "purpose": "ES contract discovery access",
    },
    {
        "name": "forex_previous_bar",
        "market": "forex",
        "path": "/v2/aggs/ticker/C:EURUSD/prev",
        "params": {"adjusted": "true"},
        "purpose": "Dollar and currency-regime context",
    },
    {
        "name": "crypto_previous_bar",
        "market": "crypto",
        "path": "/v2/aggs/ticker/X:BTCUSD/prev",
        "params": {"adjusted": "true"},
        "purpose": "Risk-regime context",
    },
    {
        "name": "indices_previous_bar",
        "market": "indices",
        "path": "/v2/aggs/ticker/I:SPX/prev",
        "params": {"adjusted": "true"},
        "purpose": "Cash-index confirmation",
    },
]


def classify(status: int, payload: dict | None) -> str:
    if 200 <= status < 300:
        return "AVAILABLE"
    if status in (401, 403):
        message = json.dumps(payload or {}).lower()
        if "not authorized" in message or "upgrade" in message or "subscription" in message:
            return "PLAN_RESTRICTED"
        return "AUTH_FAILED"
    if status == 429:
        return "RATE_LIMITED"
    if status == 404:
        return "ENDPOINT_UNAVAILABLE"
    return "ERROR"


def safe_summary(payload: dict | None) -> tuple[str | None, int | None, str | None]:
    if not isinstance(payload, dict):
        return None, None, None
    provider_status = payload.get("status")
    results = payload.get("results")
    if isinstance(results, list):
        result_count = len(results)
    elif results is None:
        result_count = None
    else:
        result_count = 1
    error_text = payload.get("error") or payload.get("message")
    if error_text:
        error_text = str(error_text)[:300]
    return provider_status, result_count, error_text


def request_check(api_key: str, check: dict) -> dict:
    query = urllib.parse.urlencode(check["params"])
    url = BASE_URL + check["path"] + ("?" + query if query else "")
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "TradingPulse-Massive-Capability-Audit/1.0",
        },
        method="GET",
    )
    started = time.perf_counter()
    status = 0
    payload = None
    transport_error = None
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            status = response.status
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        status = exc.code
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = None
    except Exception as exc:
        transport_error = f"{type(exc).__name__}: {exc}"

    provider_status, result_count, provider_error = safe_summary(payload)
    return {
        "name": check["name"],
        "market": check["market"],
        "purpose": check["purpose"],
        "endpoint": check["path"],
        "http_status": status or None,
        "access": classify(status, payload) if status else "TRANSPORT_ERROR",
        "provider_status": provider_status,
        "result_count": result_count,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "error": transport_error or provider_error,
    }


def main() -> int:
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if len(api_key) < 20:
        print("MASSIVE_API_KEY is missing or invalid.")
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = ROOT / "research_data" / "v7" / "massive" / "capability_audit" / stamp
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Trading Pulse Massive Capability Audit")
    print("Tiny read-only requests only; no bulk data download.\n")

    rows = []
    for check in CHECKS:
        row = request_check(api_key, check)
        rows.append(row)
        print(
            f"{row['name']:<26} {row['access']:<22} "
            f"HTTP={row['http_status'] or '-'} rows={row['result_count'] if row['result_count'] is not None else '-'}"
        )

    csv_path = output_dir / "massive_capability_matrix.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    available = [row["name"] for row in rows if row["access"] == "AVAILABLE"]
    restricted = [row["name"] for row in rows if row["access"] == "PLAN_RESTRICTED"]
    report = {
        "schema": SCHEMA,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE_URL,
        "request_count": len(rows),
        "bulk_downloads": 0,
        "purchases": 0,
        "api_key_recorded": False,
        "available_checks": available,
        "plan_restricted_checks": restricted,
        "checks": rows,
        "flat_file_status": "NOT_TESTED_SEPARATE_S3_CREDENTIALS_REQUIRED",
        "integration_status": "AUDIT_ONLY_NOT_PROMOTED",
        "guardrails": [
            "Databento remains canonical for existing futures research.",
            "Massive data must pass overlapping-period parity checks before promotion.",
            "Provider identity must remain attached to every stored record.",
            "No endpoint response body or API credential is stored by this audit.",
        ],
    }
    report_path = output_dir / "massive_capability_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\nOUTPUT READY: {output_dir}")
    print(f"AVAILABLE CHECKS: {len(available)}/{len(rows)}")
    print("FLAT FILES: separate S3 credentials must be audited later")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
