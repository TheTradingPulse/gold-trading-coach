from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(r"C:\TradingPulse")
RAW = ROOT / "research_data" / "v4" / "historical_blind" / "raw"
V6 = ROOT / "research_data" / "v6"
OUT = V6 / "massive_move_lab"
CHECK = OUT / "checkpoints"
SYMBOLS = ["GC", "SI", "ES", "NQ", "YM", "RTY", "CL", "NG"]


def wilson_lower(wins: int, n: int, z: float = 1.96) -> float:
    if n <= 0:
        return float("nan")
    p = wins / n
    den = 1 + z * z / n
    return (p + z*z/(2*n) - z * math.sqrt((p*(1-p) + z*z/(4*n))/n)) / den


def normalize(frame: pd.DataFrame) -> pd.DataFrame:
    x = frame.copy()
    x.columns = [str(c).lower().strip() for c in x.columns]
    aliases = {
        "timestamp": ["timestamp", "ts_event", "datetime", "date", "time"],
        "open": ["open", "o"], "high": ["high", "h"],
        "low": ["low", "l"], "close": ["close", "c"],
        "volume": ["volume", "v", "size"]
    }
    ren = {}
    for target, names in aliases.items():
        for name in names:
            if name in x.columns:
                ren[name] = target
                break
    x = x.rename(columns=ren)
    if "timestamp" not in x.columns:
        if isinstance(x.index, pd.DatetimeIndex):
            x = x.reset_index().rename(columns={x.index.name or "index": "timestamp"})
        else:
            raise ValueError("No timestamp column or DatetimeIndex")
    need = ["timestamp", "open", "high", "low", "close"]
    missing = [c for c in need if c not in x.columns]
    if missing:
        raise ValueError(f"Missing OHLC columns: {missing}")
    x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close", "volume"]:
        if c not in x.columns:
            x[c] = 0.0
        x[c] = pd.to_numeric(x[c], errors="coerce")
    return x.dropna(subset=need).sort_values("timestamp")[need + ["volume"]]


def load_symbol(symbol: str) -> pd.DataFrame:
    files = sorted(RAW.glob(f"*/{symbol}__1m.parquet"))
    if not files:
        raise FileNotFoundError(f"No one-minute files found for {symbol} under {RAW}")
    parts = []
    for i, path in enumerate(files, 1):
        parts.append(normalize(pd.read_parquet(path)))
        if i % 12 == 0 or i == len(files):
            print(f"{symbol}: loaded {i}/{len(files)} months", flush=True)
    return pd.concat(parts, ignore_index=True).drop_duplicates("timestamp", keep="last")


def sessions(symbol: str, bars: pd.DataFrame) -> pd.DataFrame:
    # CME-style trading date: the session beginning 18:00 New York belongs to
    # the following calendar trading date. DST is handled by zone conversion.
    local = bars["timestamp"].dt.tz_convert("America/New_York")
    bars = bars.copy()
    bars["session_date"] = (local + pd.Timedelta(hours=6)).dt.date
    bars["local_minute"] = local.dt.hour * 60 + local.dt.minute
    bars["bar_range"] = bars.high - bars.low

    rows = []
    prev_close = None
    for day, g in bars.groupby("session_date", sort=True):
        g = g.sort_values("timestamp")
        o, h, l, c = float(g.open.iloc[0]), float(g.high.max()), float(g.low.min()), float(g.close.iloc[-1])
        rng = h - l
        if not np.isfinite(rng) or rng <= 0:
            continue
        high_ts = g.loc[g.high.idxmax(), "timestamp"]
        low_ts = g.loc[g.low.idxmin(), "timestamp"]
        direction = 1 if c >= o else -1
        efficiency = abs(c-o) / rng
        close_location = (c-l) / rng
        directional_close = close_location if direction > 0 else 1-close_location
        gap = 0.0 if prev_close is None else o-prev_close
        first90 = g[(g.local_minute >= 570) & (g.local_minute < 660)]
        opening_range = float(first90.high.max()-first90.low.min()) if len(first90) else np.nan
        rows.append({
            "symbol": symbol, "session_date": str(day), "start_utc": str(g.timestamp.iloc[0]),
            "end_utc": str(g.timestamp.iloc[-1]), "open": o, "high": h, "low": l, "close": c,
            "range": rng, "net_move": c-o, "direction": "LONG" if direction > 0 else "SHORT",
            "efficiency": efficiency, "directional_close": directional_close,
            "volume": float(g.volume.sum()), "gap": gap, "opening_90m_range": opening_range,
            "high_first": bool(high_ts < low_ts), "high_time_utc": str(high_ts), "low_time_utc": str(low_ts),
            "minutes": int(len(g))
        })
        prev_close = c
    d = pd.DataFrame(rows)
    tr = np.maximum(d["range"], np.maximum((d.high-d.close.shift()).abs(), (d.low-d.close.shift()).abs()))
    d["prior_atr20"] = tr.shift(1).rolling(20, min_periods=10).median()
    d["prior_volume20"] = d.volume.shift(1).rolling(20, min_periods=10).median()
    d["prior_range"] = d.range.shift(1)
    d["prior_range_to_atr"] = d.prior_range / d.prior_atr20
    d["range_atr"] = d.range / d.prior_atr20
    d["volume_ratio"] = d.volume / d.prior_volume20
    d["gap_atr"] = d.gap.abs() / d.prior_atr20
    d["opening_range_atr"] = d.opening_90m_range / d.prior_atr20
    d["massive_score"] = d.range_atr * (0.5 + 0.5*d.efficiency) * (0.75 + 0.25*d.directional_close)
    # Fixed, interpretable definition. It does not learn a threshold from 2025.
    d["massive"] = (d.range_atr >= 1.75) & (d.efficiency >= 0.60) & (d.directional_close >= 0.75)
    d["trend_day"] = (d.efficiency >= 0.70) & (d.directional_close >= 0.80)
    d["period"] = np.select(
        [pd.to_datetime(d.session_date).dt.year <= 2023,
         pd.to_datetime(d.session_date).dt.year == 2024],
        ["development", "calibration"], default="holdout")
    return d


def precursor_report(all_days: pd.DataFrame) -> pd.DataFrame:
    rows = []
    tests = {
        "prior_compression": all_days.prior_range_to_atr <= 0.75,
        "prior_expansion": all_days.prior_range_to_atr >= 1.25,
        "gap_large": all_days.gap_atr >= 0.35,
        "opening_drive_large": all_days.opening_range_atr >= 0.55,
        "volume_expansion": all_days.volume_ratio >= 1.25,
    }
    for period in ["development", "calibration", "holdout"]:
        p = all_days[all_days.period == period]
        base_n, base_w = len(p), int(p.massive.sum())
        base_rate = base_w/base_n if base_n else np.nan
        for name, mask in tests.items():
            q = p[mask.reindex(p.index, fill_value=False)]
            n, w = len(q), int(q.massive.sum())
            rate = w/n if n else np.nan
            rows.append({"period": period, "precursor": name, "n": n, "massive_days": w,
                         "massive_rate": rate, "baseline_rate": base_rate,
                         "lift": rate/base_rate if n and base_rate else np.nan,
                         "wilson_lower": wilson_lower(w, n)})
    return pd.DataFrame(rows)


def copy_rr_evidence() -> dict:
    candidates = sorted(V6.glob("**/v6_subgroup_rr_matrix.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        return {"status": "not_found", "note": "Run/copy the V6 deep audit under research_data\\v6 to include it."}
    df = pd.read_csv(candidates[0])
    df.to_csv(OUT / "v6_1r_to_20r_existing_audit.csv", index=False)
    return {"status": "copied", "source": str(candidates[0]), "rows": len(df)}


def v6_schema_inventory() -> list[dict]:
    dbs = sorted(V6.glob("**/*.db"))
    inventory = []
    for db in dbs:
        try:
            con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
            for (table,) in con.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'"):
                cols = [r[1] for r in con.execute(f'pragma table_info("{table}")')]
                inventory.append({"database": str(db), "table": table, "columns": cols})
            con.close()
        except Exception as exc:
            inventory.append({"database": str(db), "error": str(exc)})
    return inventory


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    CHECK.mkdir(parents=True, exist_ok=True)
    frames = []
    for symbol in SYMBOLS:
        checkpoint = CHECK / f"{symbol}_sessions.parquet"
        if checkpoint.exists():
            print(f"{symbol}: using checkpoint {checkpoint}", flush=True)
            d = pd.read_parquet(checkpoint)
        else:
            d = sessions(symbol, load_symbol(symbol))
            d.to_parquet(checkpoint, index=False)
        frames.append(d)
        print(f"{symbol}: {len(d):,} sessions; {int(d.massive.sum()):,} massive", flush=True)

    all_days = pd.concat(frames, ignore_index=True)
    all_days.to_csv(OUT / "all_session_metrics.csv", index=False)
    ranked = all_days.sort_values(["massive", "massive_score"], ascending=False)
    ranked.to_csv(OUT / "massive_move_catalog.csv", index=False)
    queue = (ranked[ranked.massive].groupby("symbol", group_keys=False).head(30)
             .sort_values(["symbol", "massive_score"], ascending=[True, False]))
    queue.to_csv(OUT / "chart_review_queue_top30_per_symbol.csv", index=False)
    precursors = precursor_report(all_days)
    precursors.to_csv(OUT / "point_in_time_precursor_audit.csv", index=False)
    rr = copy_rr_evidence()
    schema = v6_schema_inventory()
    (OUT / "v6_schema_inventory.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")

    summary = []
    for period, p in all_days.groupby("period"):
        summary.append({"period": period, "sessions": len(p), "massive": int(p.massive.sum()),
                        "rate": float(p.massive.mean())})
    report = {
        "schema": "TP_V6_MASSIVE_MOVE_LAB_1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "definition": "range>=1.75x prior 20-session median TR; efficiency>=0.60; directional close>=0.75",
        "symbols": SYMBOLS, "summary": summary, "rr_evidence": rr,
        "research_warning": "Backward massive-move findings are hypotheses. Do not promote after viewing 2025 without a new holdout."
    }
    (OUT / "massive_move_lab_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\nTrading Pulse Massive-Move Lab", flush=True)
    for x in summary:
        print(f"{x['period']}: {x['sessions']:,} sessions | {x['massive']:,} massive | {x['rate']:.2%}")
    print(f"OUTPUT READY: {OUT}")


if __name__ == "__main__":
    main()
