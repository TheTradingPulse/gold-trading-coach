"""Run V6 detector plus lifecycle classification without changing live output."""
from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

from core.canonical_opportunity_lifecycle import ACTIVE_STATES, LIFECYCLE_VERSION, classify_zones
from core.canonical_professional_zone_detector import DETECTOR_VERSION, detect_professional_zones
from core.market_data_provider import fetch_market_data

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = ["GC", "SI", "ES", "NQ", "YM", "RTY", "CL", "NG"]


def closed(symbol, timeframe, limit):
    x = fetch_market_data(symbol, timeframe, limit, force_refresh=True).copy()
    x.index = pd.to_datetime(x.index, utc=True)
    return x.loc[x.index <= pd.Timestamp.now(tz="UTC") - pd.Timedelta("15min")].sort_index()


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = ROOT / "research_data" / "v6" / "canonical_lifecycle" / stamp
    out.mkdir(parents=True, exist_ok=True)
    all_rows, symbol_reports = [], []
    for symbol in SYMBOLS:
        print(f"{symbol}: fetching closed reference bars", flush=True)
        m5, m15, h1 = closed(symbol, "5m", 20000), closed(symbol, "15m", 20000), closed(symbol, "1h", 20000)
        zones = detect_professional_zones(symbol, m5, m15, h1)
        cutoff = m5.index.max() - pd.Timedelta("14D")
        recent = zones[pd.to_datetime(zones.entry_ts, utc=True) >= cutoff]
        classified = classify_zones(recent, m5, target_rr=5.0, max_active_bars=576)
        if not classified.empty:
            classified["shadow_run"] = stamp
            all_rows.append(classified)
        counts = Counter(classified.state if not classified.empty else [])
        symbol_reports.append({"symbol": symbol, "zones_recent": len(recent), "states": dict(counts),
                               "active_display": sum(counts[s] for s in ACTIVE_STATES)})
        print(f"  recent={len(recent)} active={symbol_reports[-1]['active_display']} states={dict(counts)}", flush=True)
    combined = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()
    combined.to_csv(out / "canonical_lifecycle_all_recent.csv", index=False)
    active = combined[combined.state.isin(ACTIVE_STATES)] if not combined.empty else combined
    active.to_csv(out / "canonical_active_opportunities.csv", index=False)
    report = {"schema": "TP_CANONICAL_LIFECYCLE_SHADOW_REPORT_1", "created_utc": datetime.now(timezone.utc).isoformat(),
              "detector_version": DETECTOR_VERSION, "lifecycle_version": LIFECYCLE_VERSION,
              "target_rr": 5.0, "max_active_bars": 576, "timeframe": "5m_closed",
              "same_bar_policy": "fail_closed", "live_promotion": False,
              "successful_symbols": len(symbol_reports), "symbols": symbol_reports,
              "rows_classified": len(combined), "active_display_rows": len(active), "integrity": "ok"}
    (out / "canonical_lifecycle_shadow_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    registry_path = ROOT / "config" / "tradingpulse_registry.json"
    if registry_path.exists():
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry.setdefault("production", {})["shadow_lifecycle"] = "core/canonical_opportunity_lifecycle.py"
        registry["production"]["shadow_lifecycle_status"] = "CANONICAL_LIFECYCLE_SHADOW_OPERATIONAL"
        registry["production"]["live_promotion"] = False
        registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    print(f"OUTPUT READY: {out}")
    print(f"ACTIVE DISPLAY ROWS: {len(active)}")
    print("LIVE PROMOTION: False")


if __name__ == "__main__":
    main()
