"""Resumable local-only standard/micro Diamond Discovery Lab."""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "research_data/v6/professional_zone_reference.db"
RAW = ROOT / "research_data/v4/historical_blind/raw"
MICRO_ROOT = ROOT / "research_data/v7/micro_5y"
MASSIVE = ROOT / "research_data/v6/massive_move_lab/all_session_metrics.csv"
OUT = ROOT / "research_data/v7/diamond_lab/overnight_20260823"
CHECK = OUT / "checkpoints"
RR_TARGETS = tuple(range(1, 21))
MIN_MATERIAL_NET_R = 0.05
MIN_SAFE_RISK_USD = 75.0
MAX_WEEKLY_OPPORTUNITIES = 5.0
MIN_WEEKLY_OPPORTUNITIES = 0.10
FILL_WAIT_MINUTES = 120
OUTCOME_MINUTES = 14400
OVERLAP_MINUTES = 240
BOOTSTRAP_CHECKPOINT_EVERY = 100

MARKETS = {
    "GC": {"micro": "MGC", "tick": 0.10, "micro_tick_value": 1.00, "commission": 2.50},
    "SI": {"micro": "SIL", "tick": 0.005, "micro_tick_value": 5.00, "commission": 2.50},
    "ES": {"micro": "MES", "tick": 0.25, "micro_tick_value": 1.25, "commission": 2.50},
    "NQ": {"micro": "MNQ", "tick": 0.25, "micro_tick_value": 0.50, "commission": 2.50},
    "YM": {"micro": "MYM", "tick": 1.00, "micro_tick_value": 0.50, "commission": 2.50},
    "RTY": {"micro": "M2K", "tick": 0.10, "micro_tick_value": 0.50, "commission": 2.50},
    "CL": {"micro": "MCL", "tick": 0.01, "micro_tick_value": 1.00, "commission": 2.50},
    "NG": {"micro": "MNG", "tick": 0.001, "micro_tick_value": 1.00, "commission": 2.50},
}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, payload):
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)


def normalize(path, columns=("open", "high", "low", "close", "volume")):
    x = pd.read_parquet(path)
    low = {str(c).lower(): c for c in x.columns}
    if "ts_event" in low:
        x = x.set_index(low["ts_event"])
    elif not isinstance(x.index, pd.DatetimeIndex):
        stamp = next((low[k] for k in ("timestamp", "datetime", "time", "date") if k in low), None)
        if stamp is None:
            raise ValueError(f"No timestamp in {path}")
        x = x.set_index(stamp)
    x.index = pd.to_datetime(x.index, utc=True, errors="coerce")
    low = {str(c).lower(): c for c in x.columns}
    found = [c for c in columns if c in low]
    x = x[[low[c] for c in found]].copy()
    x.columns = found
    if "volume" in columns and "volume" not in x:
        x["volume"] = 0.0
    for c in x.columns:
        x[c] = pd.to_numeric(x[c], errors="coerce")
    required = [c for c in ("high", "low", "close") if c in columns]
    return x.dropna(subset=required).sort_index()[lambda q: ~q.index.duplicated(keep="last")]


def micro_path(symbol):
    micro = MARKETS[symbol]["micro"]
    return MICRO_ROOT / f"{micro}_v_0_ohlcv_1m_20210101_20260101.parquet"


def load_standard(symbol):
    files = sorted(RAW.glob(f"*/{symbol}__1m.parquet"))
    if len(files) < 55:
        raise SystemExit(f"Expected five years of {symbol} standard files; found {len(files)}")
    parts = []
    for n, path in enumerate(files, 1):
        parts.append(normalize(path))
        if n % 12 == 0:
            print(f"{symbol}: standard {n}/{len(files)} months", flush=True)
    return pd.concat(parts).sort_index()[lambda q: ~q.index.duplicated(keep="last")]


def load_zones():
    if not DB.exists():
        raise SystemExit(f"Canonical reference missing: {DB}")
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    zones = pd.read_sql_query("SELECT * FROM professional_zones", con)
    con.close()
    if integrity != "ok" or len(zones) < 100000:
        raise SystemExit(f"Canonical reference failed: integrity={integrity}, rows={len(zones)}")
    zones["entry_ts"] = pd.to_datetime(zones.entry_ts, utc=True, errors="coerce")
    zones = zones.dropna(subset=["entry_ts", "symbol", "entry", "stop", "risk"])
    zones["year"] = zones.entry_ts.dt.year
    zones = zones[zones.year.between(2021, 2025) & zones.symbol.isin(MARKETS)].copy()
    zones = zones[zones.terminal.ne("not_entered")]
    return zones, integrity


def purge_overlaps(df):
    kept = []
    gap = pd.Timedelta(minutes=OVERLAP_MINUTES)
    ordered = df.sort_values(["symbol", "entry_ts", "ota_score"], ascending=[True, True, False])
    for _, group in ordered.groupby("symbol"):
        cluster, start = [], None
        for idx, row in group.iterrows():
            if start is None or row.entry_ts - start < gap:
                cluster.append((idx, float(row.ota_score), float(row.profit_room_r)))
                if start is None:
                    start = row.entry_ts
            else:
                kept.append(max(cluster, key=lambda z: (z[1], z[2]))[0])
                cluster, start = [(idx, float(row.ota_score), float(row.profit_room_r))], row.entry_ts
        if cluster:
            kept.append(max(cluster, key=lambda z: (z[1], z[2]))[0])
    return df.loc[sorted(kept)].copy()


def prior_close(frame, ts, tolerance_minutes=10):
    pos = frame.index.searchsorted(ts, side="right") - 1
    if pos < 0:
        return None
    if ts - frame.index[pos] > pd.Timedelta(minutes=tolerance_minutes):
        return None
    return float(frame.close.iloc[pos])


def replay_micro(index, high, low, start_ts, direction, entry, stop, risk):
    begin = index.searchsorted(start_ts, side="left")
    entered = None
    for j in range(begin, min(len(index), begin + FILL_WAIT_MINUTES)):
        if float(low[j]) <= entry <= float(high[j]):
            entered = j
            break
    if entered is None:
        return None, "not_filled", 0, 0
    verified = possible = 0
    terminal = "open"
    for j in range(entered, min(len(index), entered + OUTCOME_MINUTES)):
        favorable = (float(high[j]) - entry) / risk if direction == "LONG" else (entry - float(low[j])) / risk
        reached = max(0, min(20, int(math.floor(favorable + 1e-10))))
        stop_hit = float(low[j]) <= stop if direction == "LONG" else float(high[j]) >= stop
        if j == entered:
            possible = max(possible, reached)
            if stop_hit:
                terminal = "stopped"
                break
            continue
        if stop_hit:
            possible = max(possible, reached)
            terminal = "stopped"
            break
        verified = max(verified, reached)
        possible = max(possible, verified)
        if verified >= 20:
            terminal = "20r_verified"
            break
    return index[entered], terminal, verified, possible


def micro_replay_symbol(symbol, zones):
    checkpoint = CHECK / f"{symbol}_micro_consensus.parquet"
    if checkpoint.exists():
        print(f"{symbol}: using replay checkpoint", flush=True)
        return pd.read_parquet(checkpoint)
    standard = load_standard(symbol)
    mpath = micro_path(symbol)
    if not mpath.exists():
        raise SystemExit(f"Five-year micro file missing: {mpath}")
    micro = normalize(mpath)
    index = micro.index
    high, low = micro.high.to_numpy(float), micro.low.to_numpy(float)
    rows = []
    for n, row in enumerate(zones.sort_values("entry_ts").itertuples(index=False), 1):
        standard_close = prior_close(standard, row.entry_ts)
        micro_close = prior_close(micro, row.entry_ts)
        if standard_close is None or micro_close is None:
            rows.append({"zone_id": row.zone_id, "micro_terminal": "mapping_missing", "micro_verified_r": 0, "micro_possible_r": 0})
            continue
        delta = micro_close - standard_close
        entry = float(row.entry) + delta
        risk = abs(float(row.risk))
        stop = entry - risk if str(row.direction).upper() == "LONG" else entry + risk
        fill, terminal, verified, possible = replay_micro(index, high, low, row.entry_ts, str(row.direction).upper(), entry, stop, risk)
        rows.append({
            "zone_id": row.zone_id,
            "micro_symbol": MARKETS[symbol]["micro"],
            "micro_fill_ts": fill,
            "mapping_delta": delta,
            "micro_entry": entry,
            "micro_stop": stop,
            "micro_terminal": terminal,
            "micro_verified_r": verified,
            "micro_possible_r": possible,
        })
        if n % 1000 == 0:
            print(f"{symbol}: replayed {n:,}/{len(zones):,}", flush=True)
    result = pd.DataFrame(rows)
    result.to_parquet(checkpoint, index=False)
    print(f"{symbol}: checkpoint ready ({len(result):,})", flush=True)
    return result


def add_context(zones):
    x = zones.copy()
    x["period"] = np.where(x.year <= 2023, "development", np.where(x.year == 2024, "calibration", "holdout"))
    et = x.entry_ts.dt.tz_convert("America/New_York")
    x["session"] = pd.cut(et.dt.hour, [-1, 2, 7, 12, 16, 23], labels=["overnight", "europe", "new_york_am", "new_york_pm", "evening"])
    x["session_date"] = (et + pd.Timedelta(hours=6)).dt.date.astype(str)
    x["month"] = x.entry_ts.dt.to_period("M").astype(str)
    x["standard_verified_r"] = pd.to_numeric(x.max_verified_r, errors="coerce").fillna(0)
    x["standard_possible_r"] = pd.to_numeric(x.max_possible_r, errors="coerce").fillna(x.standard_verified_r)
    x["consensus_verified_r"] = np.minimum(x.standard_verified_r, x.micro_verified_r)
    x["consensus_possible_r"] = np.minimum(x.standard_possible_r, x.micro_possible_r)
    if MASSIVE.exists():
        days = pd.read_csv(MASSIVE)
        keep = [c for c in ("symbol", "session_date", "massive", "massive_score", "range_atr", "efficiency", "direction") if c in days]
        days = days[keep].rename(columns={"direction": "massive_day_direction"})
        x = x.merge(days, on=["symbol", "session_date"], how="left", validate="many_to_one")
    if "massive" not in x:
        x["massive"] = False
    x["massive"] = x.massive.fillna(False).astype(bool)
    if "massive_day_direction" not in x:
        x["massive_day_direction"] = ""
    x["massive_direction_aligned"] = x.direction.astype(str).str.upper().eq(x.massive_day_direction.astype(str).str.upper())
    return x


def add_costs(x):
    x = x.copy()
    ticks = []
    base, stress = [], []
    for row in x.itertuples(index=False):
        spec = MARKETS[row.symbol]
        risk_ticks = max(abs(float(row.risk)) / spec["tick"], 1.0)
        risk_dollars = risk_ticks * spec["micro_tick_value"]
        ticks.append(risk_ticks)
        base.append((spec["commission"] + 2 * spec["micro_tick_value"]) / risk_dollars)
        stress.append((spec["commission"] + 4 * spec["micro_tick_value"]) / risk_dollars)
    x["micro_risk_ticks"] = ticks
    x["micro_cost_r"] = base
    x["micro_stress_cost_r"] = stress
    return x


def wilson_lower(wins, n, z=1.96):
    if n <= 0:
        return 0.0
    p = wins / n
    den = 1 + z * z / n
    return max(0.0, (p + z*z/(2*n) - z*math.sqrt((p*(1-p) + z*z/(4*n))/n)) / den)


def outcome_arrays(frame, rr):
    win = frame.consensus_verified_r.to_numpy(float) >= rr
    ambiguous = (~win) & (frame.consensus_possible_r.to_numpy(float) >= rr)
    stopped = frame.micro_terminal.astype(str).eq("stopped").to_numpy() | frame.terminal.astype(str).eq("stopped").to_numpy()
    eligible = (win | stopped) & (~ambiguous) & frame.micro_terminal.astype(str).ne("not_filled").to_numpy()
    return win, ambiguous, eligible


def metrics(frame, rr):
    if frame.empty:
        return {"n": 0, "wins": 0, "win_rate": 0.0, "net_expectancy_r": -1.0, "stress_expectancy_r": -1.0,
                "wilson_stress_expectancy_r": -1.0, "max_drawdown_r": 0.0, "worst_day_r": 0.0,
                "safe_risk_usd": 0.0, "opportunities_per_week": 0.0, "ambiguous": 0}
    win, ambiguous, eligible = outcome_arrays(frame, rr)
    use = frame.loc[eligible].copy()
    use_win = win[eligible]
    n, wins = len(use), int(use_win.sum())
    rate = wins / n if n else 0.0
    base_cost = float(use.micro_cost_r.mean()) if n else 0.0
    stress_cost = float(use.micro_stress_cost_r.mean()) if n else 0.0
    results = np.where(use_win, rr - use.micro_stress_cost_r.to_numpy(float), -1 - use.micro_stress_cost_r.to_numpy(float)) if n else np.array([])
    equity = np.cumsum(results)
    drawdown = equity - np.maximum.accumulate(np.r_[0.0, equity])[-len(equity):] if n else np.array([])
    max_dd = float(drawdown.min()) if n else 0.0
    if n:
        by_day = pd.DataFrame({"day": pd.to_datetime(use.entry_ts, utc=True).dt.date, "r": results}).groupby("day").r.sum()
        worst_day = float(by_day.min())
    else:
        worst_day = 0.0
    dd_capacity = 2000 / abs(max_dd) if max_dd < 0 else 2000.0
    day_capacity = 1000 / abs(worst_day) if worst_day < 0 else 1000.0
    safe_risk = 0.80 * min(dd_capacity, day_capacity)
    years = max(1.0, (pd.to_datetime(frame.entry_ts).max() - pd.to_datetime(frame.entry_ts).min()).days / 365.25) if len(frame) > 1 else 1.0
    weeks = years * 52.1775
    lower = wilson_lower(wins, n)
    return {
        "n": n, "wins": wins, "win_rate": rate,
        "net_expectancy_r": (rr + 1) * rate - 1 - base_cost,
        "stress_expectancy_r": (rr + 1) * rate - 1 - stress_cost,
        "wilson_stress_expectancy_r": (rr + 1) * lower - 1 - stress_cost,
        "max_drawdown_r": max_dd, "worst_day_r": worst_day,
        "safe_risk_usd": safe_risk, "opportunities_per_week": n / weeks,
        "ambiguous": int(ambiguous.sum()),
    }


def feature_masks(dev):
    masks = []
    categorical = ["symbol", "pattern", "direction", "curve_position", "base_candles", "session"]
    for column in categorical:
        if column not in dev:
            continue
        for value in dev[column].dropna().unique():
            mask = dev[column].astype(str).eq(str(value)).to_numpy()
            masks.append((f"{column}={value}", mask, (column, "eq", value)))
    numeric = ["ota_score", "strength_score", "trend_score", "freshness_score", "departure_ratio", "profit_room_r", "micro_risk_ticks"]
    for column in numeric:
        if column not in dev or dev[column].dropna().nunique() < 10:
            continue
        values = pd.to_numeric(dev[column], errors="coerce")
        for quantile in (0.50, 0.65, 0.75, 0.85, 0.90):
            threshold = float(values.quantile(quantile))
            mask = values.ge(threshold).fillna(False).to_numpy()
            masks.append((f"{column}>={threshold:.6g}", mask, (column, "gte", threshold)))
    return masks


def apply_rule(frame, clauses):
    mask = np.ones(len(frame), dtype=bool)
    for column, operation, value in clauses:
        if operation == "eq":
            mask &= frame[column].astype(str).eq(str(value)).to_numpy()
        else:
            mask &= pd.to_numeric(frame[column], errors="coerce").ge(float(value)).fillna(False).to_numpy()
    return frame.loc[mask]


def discover_candidates(data):
    dev = data[data.period == "development"].reset_index(drop=True)
    calibration = data[data.period == "calibration"]
    holdout = data[data.period == "holdout"]
    singles = feature_masks(dev)
    seed_rows = []
    for rr in RR_TARGETS:
        baseline = metrics(dev, rr)
        for label, mask, clause in singles:
            sample = dev.loc[mask]
            result = metrics(sample, rr)
            if result["n"] >= 80 and result["stress_expectancy_r"] >= baseline["stress_expectancy_r"] + MIN_MATERIAL_NET_R:
                seed_rows.append((result["stress_expectancy_r"], rr, label, (clause,)))
    seed_rows.sort(reverse=True, key=lambda x: x[0])
    seeds = seed_rows[:80]
    rules = {(rr, clauses): label for _, rr, label, clauses in seeds}
    for i, first in enumerate(seeds[:40]):
        for second in seeds[i+1:40]:
            if first[1] != second[1]:
                continue
            clauses = tuple(dict.fromkeys(first[3] + second[3]))
            if len(clauses) != 2:
                continue
            rules[(first[1], clauses)] = f"{first[2]} AND {second[2]}"
    rows = []
    for (rr, clauses), label in rules.items():
        dm = metrics(apply_rule(dev, clauses), rr)
        cm = metrics(apply_rule(calibration, clauses), rr)
        hm = metrics(apply_rule(holdout, clauses), rr)
        frequency_ok = MIN_WEEKLY_OPPORTUNITIES <= hm["opportunities_per_week"] <= MAX_WEEKLY_OPPORTUNITIES
        material = dm["stress_expectancy_r"] >= MIN_MATERIAL_NET_R and cm["stress_expectancy_r"] >= MIN_MATERIAL_NET_R
        holdout_positive = hm["stress_expectancy_r"] > 0
        apex_feasible = hm["safe_risk_usd"] >= MIN_SAFE_RISK_USD
        rows.append({
            "candidate_id": f"D{len(rows)+1:04d}", "rr": rr, "rule": label,
            "clauses_json": json.dumps(clauses, default=str),
            "material_preholdout": material, "holdout_positive": holdout_positive,
            "frequency_ok": frequency_ok, "apex_feasible_75usd": apex_feasible,
            "research_qualified": bool(material and holdout_positive and frequency_ok and apex_feasible),
            **{f"development_{k}": v for k, v in dm.items()},
            **{f"calibration_{k}": v for k, v in cm.items()},
            **{f"holdout_{k}": v for k, v in hm.items()},
        })
    result = pd.DataFrame(rows)
    if len(result):
        result = result.sort_values(["research_qualified", "holdout_stress_expectancy_r", "holdout_n"], ascending=[False, False, False])
    return result


def massive_fingerprints(data):
    massive = data[data.massive & data.massive_direction_aligned].copy()
    massive["diamond_r"] = np.minimum(massive.consensus_verified_r, 20)
    columns = [c for c in ("symbol", "session_date", "zone_id", "entry_ts", "pattern", "direction", "session", "ota_score", "departure_ratio", "profit_room_r", "micro_risk_ticks", "diamond_r", "massive_score", "range_atr", "efficiency") if c in massive]
    return massive.sort_values(["diamond_r", "massive_score"], ascending=False)[columns]


def bootstrap_until_deadline(data, candidates, deadline):
    path = CHECK / "bootstrap_state.json"
    state = {"iterations": 0, "candidates": {}}
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
    if candidates.empty:
        return state
    top = candidates.head(40).copy()
    months = sorted(data.month.dropna().unique())
    rng = np.random.default_rng(20260823 + int(state.get("iterations", 0)))
    while time.time() < deadline - 60:
        sampled_months = rng.choice(months, size=len(months), replace=True)
        sample = pd.concat([data[data.month == month] for month in sampled_months], ignore_index=True)
        for row in top.itertuples(index=False):
            clauses = json.loads(row.clauses_json)
            result = metrics(apply_rule(sample, clauses), int(row.rr))
            slot = state["candidates"].setdefault(row.candidate_id, {"positive": 0, "material": 0, "sum_expectancy": 0.0, "samples": 0})
            slot["positive"] += int(result["stress_expectancy_r"] > 0)
            slot["material"] += int(result["stress_expectancy_r"] >= MIN_MATERIAL_NET_R)
            slot["sum_expectancy"] += result["stress_expectancy_r"]
            slot["samples"] += 1
        state["iterations"] = int(state.get("iterations", 0)) + 1
        if state["iterations"] % BOOTSTRAP_CHECKPOINT_EVERY == 0:
            state["updated_utc"] = utcnow()
            atomic_json(path, state)
            print(f"Bootstrap iterations: {state['iterations']:,}", flush=True)
    state["updated_utc"] = utcnow()
    atomic_json(path, state)
    return state


def main(hours):
    started = time.time()
    deadline = started + hours * 3600
    OUT.mkdir(parents=True, exist_ok=True)
    CHECK.mkdir(parents=True, exist_ok=True)
    state_path = OUT / "run_state.json"
    atomic_json(state_path, {"schema": "TP_PHASE3L_STATE_1", "status": "running", "started_utc": utcnow(), "deadline_utc": datetime.fromtimestamp(deadline, timezone.utc).isoformat(), "hours": hours})

    zones, integrity = load_zones()
    zones = purge_overlaps(zones)
    print(f"Canonical overlap-purged zones: {len(zones):,}", flush=True)
    replay_parts = []
    for symbol in MARKETS:
        subset = zones[zones.symbol == symbol].copy()
        replay_parts.append(micro_replay_symbol(symbol, subset))
        if time.time() >= deadline - 300:
            print("Runtime boundary reached during replay; checkpoints preserved.", flush=True)
            atomic_json(state_path, {"status": "checkpointed", "updated_utc": utcnow(), "next_action": "rerun same command to resume"})
            return 0

    replay = pd.concat(replay_parts, ignore_index=True)
    data = zones.merge(replay, on="zone_id", how="left", validate="one_to_one")
    data = add_costs(add_context(data))
    data.to_parquet(CHECK / "consensus_dataset.parquet", index=False)
    fingerprints = massive_fingerprints(data)
    fingerprints.to_csv(OUT / "massive_move_diamond_fingerprints.csv", index=False)
    candidates = discover_candidates(data)
    candidates.to_csv(OUT / "diamond_candidate_validation.csv", index=False)

    bootstrap = bootstrap_until_deadline(data, candidates, deadline)
    bootstrap_rows = []
    for candidate_id, stats in bootstrap.get("candidates", {}).items():
        n = max(1, stats["samples"])
        bootstrap_rows.append({"candidate_id": candidate_id, "samples": stats["samples"], "positive_fraction": stats["positive"] / n, "material_fraction": stats["material"] / n, "mean_stress_expectancy_r": stats["sum_expectancy"] / n})
    bootstrap_df = pd.DataFrame(bootstrap_rows)
    bootstrap_df.to_csv(OUT / "diamond_bootstrap_stability.csv", index=False)
    if len(candidates) and len(bootstrap_df):
        final = candidates.merge(bootstrap_df, on="candidate_id", how="left")
        final["diamond_finalist"] = final.research_qualified & final.positive_fraction.ge(0.90) & final.material_fraction.ge(0.70)
    else:
        final = candidates.copy()
        final["diamond_finalist"] = False
    final.to_csv(OUT / "diamond_final_rankings.csv", index=False)

    report = {
        "schema": "TP_PHASE3L_OVERNIGHT_DIAMOND_LAB_1", "created_utc": utcnow(),
        "runtime_hours": (time.time() - started) / 3600, "requested_hours": hours,
        "canonical_integrity": integrity, "overlap_purged_zones": len(zones),
        "micro_replayed": int(replay.micro_terminal.notna().sum()),
        "rr_targets": list(RR_TARGETS), "standard_micro_consensus": True,
        "massive_fingerprints": len(fingerprints), "candidate_rules": len(candidates),
        "research_qualified": int(candidates.research_qualified.sum()) if len(candidates) else 0,
        "bootstrap_iterations": bootstrap.get("iterations", 0),
        "diamond_finalists": int(final.diamond_finalist.sum()) if len(final) else 0,
        "material_improvement_r": MIN_MATERIAL_NET_R,
        "frequency_target_per_week": [MIN_WEEKLY_OPPORTUNITIES, MAX_WEEKLY_OPPORTUNITIES],
        "minimum_apex_safe_risk_usd": MIN_SAFE_RISK_USD,
        "external_data_purchased": False, "dashboard_modified": False,
        "live_promotion": False, "integrity": "ok",
        "warning": "Massive-move membership is descriptive outcome information and is never used as a point-in-time filter. Finalists remain research-only pending review.",
    }
    atomic_json(OUT / "diamond_lab_report.json", report)
    atomic_json(state_path, {"schema": "TP_PHASE3L_STATE_1", "status": "complete", "completed_utc": utcnow(), "result": report})
    print(f"OUTPUT READY: {OUT}", flush=True)
    print(f"DIAMOND FINALISTS: {report['diamond_finalists']}", flush=True)
    print("LIVE PROMOTION: False", flush=True)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=10.0)
    args = parser.parse_args()
    if not 0.25 <= args.hours <= 12.0:
        raise SystemExit("Hours must be between 0.25 and 12")
    raise SystemExit(main(args.hours))
