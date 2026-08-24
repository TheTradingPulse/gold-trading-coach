"""Native 1R-20R first-touch ladder plus chronological filter discovery."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from core.canonical_opportunity_lifecycle import classify_zones
from core.canonical_professional_zone_detector import DETECTOR_VERSION, detect_professional_zones
from core.market_data_provider import fetch_market_data

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = ["GC", "SI", "ES", "NQ", "YM", "RTY", "CL", "NG"]
MIN_DEVELOPMENT_N = 25
MIN_VALIDATION_N = 10


def wilson_lower(wins: int, total: int, z: float = 1.96) -> float:
    if total <= 0:
        return 0.0
    p = wins / total
    den = 1 + z * z / total
    centre = p + z * z / (2 * total)
    radius = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    return max(0.0, (centre - radius) / den)


def closed(symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    x = fetch_market_data(symbol, timeframe, limit, force_refresh=True).copy()
    x.index = pd.to_datetime(x.index, utc=True)
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta("15min")
    return x.loc[x.index <= cutoff].sort_index()


def metrics(x: pd.DataFrame, rr: int) -> dict:
    resolved = x[x.state.isin(["RESOLVED_TARGET", "RESOLVED_STOP"])]
    wins = int((resolved.state == "RESOLVED_TARGET").sum())
    n = len(resolved)
    rate = wins / n if n else 0.0
    wl = wilson_lower(wins, n)
    return {"n": n, "wins": wins, "losses": n - wins,
            "win_rate": rate, "wilson_lower": wl,
            "expectancy_r": rate * rr - (1 - rate),
            "wilson_expectancy_r": wl * rr - (1 - wl),
            "ambiguous": int((x.state == "SAME_BAR_AMBIGUOUS").sum()),
            "unresolved": int(x.state.isin(["TRIGGERED_RECENT", "ACTIVE_RISK", "MANAGING"]).sum())}


def chronological_split(df: pd.DataFrame) -> pd.DataFrame:
    x = df.sort_values("entry_ts").copy()
    unique_ts = np.array(sorted(x.entry_ts.unique()))
    if len(unique_ts) < 5:
        x["split"] = "development"
        return x
    c1 = unique_ts[max(0, int(len(unique_ts) * .60) - 1)]
    c2 = unique_ts[max(0, int(len(unique_ts) * .80) - 1)]
    x["split"] = np.where(x.entry_ts <= c1, "development",
                           np.where(x.entry_ts <= c2, "calibration", "holdout"))
    return x


def feature_values(df: pd.DataFrame) -> list[tuple[str, object]]:
    values = []
    for col in ["symbol", "pattern", "direction", "curve_position", "base_candles"]:
        if col in df:
            values.extend((col, v) for v in df[col].dropna().unique())
    for col in ["ota_score", "strength_score", "trend_score", "freshness_score",
                "departure_ratio", "profit_room_r", "risk_ticks"]:
        if col not in df or df[col].dropna().nunique() < 4:
            continue
        for q in (.25, .50, .75):
            threshold = float(df[col].quantile(q))
            values.append((f"{col}__gte", threshold))
    return values


def apply_feature(df: pd.DataFrame, name: str, value: object) -> pd.DataFrame:
    if name.endswith("__gte"):
        return df[df[name[:-5]] >= float(value)]
    return df[df[name] == value]


def discover_filters(rr_df: pd.DataFrame, rr: int) -> list[dict]:
    candidates = []
    dev = rr_df[rr_df.split == "development"]
    base = metrics(dev, rr)
    for name, value in feature_values(dev):
        d = apply_feature(dev, name, value)
        dm = metrics(d, rr)
        if dm["n"] < MIN_DEVELOPMENT_N or dm["expectancy_r"] <= base["expectancy_r"]:
            continue
        cal = apply_feature(rr_df[rr_df.split == "calibration"], name, value)
        cm = metrics(cal, rr)
        if cm["n"] < MIN_VALIDATION_N or cm["expectancy_r"] <= 0:
            continue
        hold = apply_feature(rr_df[rr_df.split == "holdout"], name, value)
        hm = metrics(hold, rr)
        candidates.append({"rr": rr, "feature": name, "value": value,
                           "development": dm, "calibration": cm, "holdout": hm,
                           "holdout_positive": hm["n"] >= MIN_VALIDATION_N and hm["expectancy_r"] > 0,
                           "promotable": hm["n"] >= MIN_VALIDATION_N and hm["wilson_expectancy_r"] > 0})
    return sorted(candidates, key=lambda z: (z["promotable"], z["holdout"]["expectancy_r"], z["holdout"]["n"]), reverse=True)


def main() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = ROOT / "research_data" / "v6" / "canonical_rr_filter_lab" / stamp
    out.mkdir(parents=True, exist_ok=True)
    frames: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
    for symbol in SYMBOLS:
        print(f"{symbol}: fetching closed reference bars", flush=True)
        m5 = closed(symbol, "5m", 20000)
        zones = detect_professional_zones(symbol, m5, closed(symbol, "15m", 20000), closed(symbol, "1h", 20000))
        cutoff = m5.index.max() - pd.Timedelta("14D")
        zones = zones[pd.to_datetime(zones.entry_ts, utc=True) >= cutoff].copy()
        frames[symbol] = (zones, m5)
        print(f"  eligible triggered zones={len(zones)}", flush=True)

    detail, ladder, filters = [], [], []
    for rr in range(1, 21):
        rr_parts = []
        print(f"{rr}R: native first-touch classification", flush=True)
        for symbol, (zones, m5) in frames.items():
            classified = classify_zones(zones, m5, target_rr=float(rr), max_active_bars=576)
            classified["rr"] = rr
            classified["entry_ts"] = pd.to_datetime(classified.entry_ts, utc=True)
            rr_parts.append(classified)
            sm = metrics(classified, rr)
            ladder.append({"scope": symbol, "rr": rr, **sm})
        combined = chronological_split(pd.concat(rr_parts, ignore_index=True))
        detail.append(combined)
        overall = metrics(combined, rr)
        ladder.append({"scope": "ALL", "rr": rr, **overall})
        filters.extend(discover_filters(combined, rr))
        print(f"  resolved={overall['n']} win={overall['win_rate']:.2%} exp={overall['expectancy_r']:+.3f}R ambiguous={overall['ambiguous']}", flush=True)

    detail_df = pd.concat(detail, ignore_index=True)
    ladder_df = pd.DataFrame(ladder)
    detail_df.to_csv(out / "rr_1_20_native_outcomes.csv", index=False)
    ladder_df.to_csv(out / "rr_1_20_ladder.csv", index=False)
    (out / "validated_filter_candidates.json").write_text(json.dumps(filters, indent=2, default=str), encoding="utf-8")
    flat = []
    for f in filters:
        flat.append({"rr": f["rr"], "feature": f["feature"], "value": f["value"],
                     "development_n": f["development"]["n"], "development_expectancy_r": f["development"]["expectancy_r"],
                     "calibration_n": f["calibration"]["n"], "calibration_expectancy_r": f["calibration"]["expectancy_r"],
                     "holdout_n": f["holdout"]["n"], "holdout_win_rate": f["holdout"]["win_rate"],
                     "holdout_expectancy_r": f["holdout"]["expectancy_r"],
                     "holdout_wilson_expectancy_r": f["holdout"]["wilson_expectancy_r"],
                     "promotable": f["promotable"]})
    pd.DataFrame(flat).to_csv(out / "validated_filter_candidates.csv", index=False)
    report = {"schema": "TP_CANONICAL_RR_FILTER_LAB_1", "created_utc": datetime.now(timezone.utc).isoformat(),
              "detector_version": DETECTOR_VERSION, "rr_targets": list(range(1, 21)),
              "ordering": "native_closed_5m_first_touch", "same_bar_policy": "excluded_ambiguous",
              "split": "chronological_60_20_20", "filter_search": "development_only_then_calibration_and_holdout",
              "minimum_development_n": MIN_DEVELOPMENT_N, "minimum_validation_n": MIN_VALIDATION_N,
              "candidate_filters": len(filters), "promotable_filters": sum(bool(x["promotable"]) for x in filters),
              "live_promotion": False, "integrity": "ok"}
    (out / "rr_filter_lab_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"OUTPUT READY: {out}")
    print(f"FILTER CANDIDATES: {len(filters)}")
    print(f"PROMOTABLE FILTERS: {report['promotable_filters']}")
    print("LIVE PROMOTION: False")


if __name__ == "__main__":
    main()
