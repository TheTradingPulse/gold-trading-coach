"""Full-history falsification of Phase 3D/E filter candidates."""
from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "research_data" / "v6" / "professional_zone_reference.db"
LAB_ROOT = ROOT / "research_data" / "v6" / "canonical_rr_filter_lab"
OUT_ROOT = ROOT / "research_data" / "v6" / "canonical_phase3f"
SYMBOLS = ("GC", "SI", "ES", "NQ", "YM", "RTY", "CL", "NG")
TICK_VALUE = {"GC": 10.0, "SI": 25.0, "ES": 12.5, "NQ": 5.0,
              "YM": 5.0, "RTY": 5.0, "CL": 10.0, "NG": 10.0}
ROUND_TRIP_COMMISSION = {"GC": 5.0, "SI": 5.0, "ES": 4.5, "NQ": 4.5,
                         "YM": 4.5, "RTY": 4.5, "CL": 5.0, "NG": 5.0}
TOTAL_TESTS = 157


def wilson_lower(w: int, n: int, z: float) -> float:
    if n <= 0:
        return 0.0
    p = w / n
    den = 1 + z * z / n
    return max(0.0, (p + z*z/(2*n) - z*math.sqrt((p*(1-p)+z*z/(4*n))/n)) / den)


def latest_candidates() -> Path:
    paths = sorted(LAB_ROOT.glob("*/validated_filter_candidates.csv"), key=lambda p: p.stat().st_mtime)
    if not paths:
        raise SystemExit(f"Phase 3D/E candidates missing beneath {LAB_ROOT}")
    return paths[-1]


def apply_filter(df: pd.DataFrame, feature: str, value: object) -> pd.DataFrame:
    if feature.endswith("__gte"):
        return df[pd.to_numeric(df[feature[:-5]], errors="coerce") >= float(value)]
    col = df[feature]
    if pd.api.types.is_numeric_dtype(col):
        return df[np.isclose(col.astype(float), float(value))]
    return df[col.astype(str) == str(value)]


def add_costs(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    tv = x.symbol.map(TICK_VALUE).astype(float)
    commission = x.symbol.map(ROUND_TRIP_COMMISSION).astype(float)
    risk_dollars = x.risk_ticks.astype(float) * tv
    x["cost_r_base"] = (commission + 2.0 * tv) / risk_dollars       # one tick each side
    x["cost_r_stress"] = (commission + 4.0 * tv) / risk_dollars     # two ticks each side
    return x


def purge_entries(df: pd.DataFrame, minutes: int = 240) -> pd.DataFrame:
    """Keep the highest known-at-entry score inside each symbol/time cluster."""
    kept = []
    gap = pd.Timedelta(minutes=minutes)
    for _, g in df.sort_values(["symbol", "entry_ts", "ota_score"], ascending=[True, True, False]).groupby("symbol"):
        cluster = []
        start = None
        for idx, row in g.iterrows():
            if start is None or row.entry_ts - start < gap:
                cluster.append((idx, row.ota_score, row.profit_room_r))
                if start is None:
                    start = row.entry_ts
            else:
                kept.append(max(cluster, key=lambda z: (z[1], z[2]))[0])
                cluster = [(idx, row.ota_score, row.profit_room_r)]
                start = row.entry_ts
        if cluster:
            kept.append(max(cluster, key=lambda z: (z[1], z[2]))[0])
    return df.loc[sorted(kept)].copy()


def metric(g: pd.DataFrame, rr: int, z: float = 1.96) -> dict:
    win = g.max_verified_r.ge(rr)
    amb = (~win) & g.max_possible_r.ge(rr)
    loss = (~win) & (~amb) & g.terminal.eq("stopped")
    eligible = win | amb | loss
    zdf = g[eligible]
    w, a, n = int(win.sum()), int(amb.sum()), int(eligible.sum())
    rate = w/n if n else 0.0
    lower = wilson_lower(w, n, z)
    base_cost = float(zdf.cost_r_base.mean()) if n else 0.0
    stress_cost = float(zdf.cost_r_stress.mean()) if n else 0.0
    return {"n": n, "wins": w, "losses": n-w-a, "ambiguous": a,
            "win_rate": rate, "wilson_lower": lower,
            "gross_expectancy_r": (rr+1)*rate-1,
            "base_cost_r": base_cost, "stress_cost_r": stress_cost,
            "net_expectancy_r": (rr+1)*rate-1-base_cost,
            "stress_expectancy_r": (rr+1)*rate-1-stress_cost,
            "wilson_net_expectancy_r": (rr+1)*lower-1-base_cost}


def evaluate_slices(g: pd.DataFrame, rr: int, z: float) -> tuple[list[dict], dict]:
    rows = []
    for period, p in g.groupby("period"):
        rows.append({"slice": "period", "value": period, **metric(p, rr, z)})
    for year, p in g.groupby("year"):
        rows.append({"slice": "year", "value": str(year), **metric(p, rr, z)})
    for symbol, p in g.groupby("symbol"):
        rows.append({"slice": "symbol", "value": symbol, **metric(p, rr, z)})
    for session, p in g.groupby("session", observed=True):
        rows.append({"slice": "session", "value": str(session), **metric(p, rr, z)})
    holdout = g[g.period == "holdout"]
    loo = []
    for symbol in SYMBOLS:
        q = holdout[holdout.symbol != symbol]
        if len(q):
            loo.append({"excluded": symbol, **metric(q, rr, z)})
    min_loo = min((x["stress_expectancy_r"] for x in loo if x["n"] >= 75), default=float("nan"))
    return rows, {"leave_one_market_out": loo, "minimum_loo_stress_expectancy_r": min_loo}


def main() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = OUT_ROOT / stamp
    out.mkdir(parents=True, exist_ok=True)
    if not DB.exists():
        raise SystemExit(f"Canonical V6 reference missing: {DB}")
    con = sqlite3.connect(DB)
    integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    zones = pd.read_sql_query("SELECT * FROM professional_zones", con)
    con.close()
    if integrity != "ok" or len(zones) < 100000:
        raise SystemExit(f"Reference validation failed: integrity={integrity}, rows={len(zones)}")
    zones.entry_ts = pd.to_datetime(zones.entry_ts, utc=True)
    zones["year"] = zones.entry_ts.dt.year
    zones = zones[zones.year.between(2021, 2025) & zones.terminal.ne("not_entered")].copy()
    zones["period"] = np.where(zones.year <= 2023, "development",
                               np.where(zones.year == 2024, "calibration", "holdout"))
    et = zones.entry_ts.dt.tz_convert("America/New_York")
    zones["session"] = pd.cut(et.dt.hour, [-1,2,7,12,16,23],
                              labels=["overnight","europe","new_york_am","new_york_pm","evening"])
    zones = add_costs(zones)

    cpath = latest_candidates()
    candidates = pd.read_csv(cpath)
    candidates = candidates[candidates.promotable.astype(str).str.lower().eq("true")].copy()
    z_standard = NormalDist().inv_cdf(1 - .05 / TOTAL_TESTS)
    summaries, slice_rows, loo_json = [], [], []
    for i, c in candidates.reset_index(drop=True).iterrows():
        rr, feature, value = int(c.rr), str(c.feature), c.value
        g = apply_filter(zones, feature, value)
        gp = purge_entries(g, 240)
        periods = {p: metric(q, rr, z_standard) for p, q in gp.groupby("period")}
        slices, loo = evaluate_slices(gp, rr, z_standard)
        candidate_id = f"F{i+1:03d}_{rr}R_{feature}_{value}"
        for row in slices:
            slice_rows.append({"candidate_id": candidate_id, "rr": rr, "feature": feature, "filter_value": value, **row})
        loo_json.append({"candidate_id": candidate_id, **loo})
        required = all(p in periods and periods[p]["n"] >= n for p, n in
                       (("development",500),("calibration",150),("holdout",150)))
        positive_all = required and all(periods[p]["stress_expectancy_r"] > 0 for p in periods)
        adjusted_holdout = required and periods["holdout"]["wilson_net_expectancy_r"] > 0
        general = feature != "symbol"
        loo_pass = (not general) or (math.isfinite(loo["minimum_loo_stress_expectancy_r"]) and loo["minimum_loo_stress_expectancy_r"] > 0)
        survived = bool(positive_all and adjusted_holdout and loo_pass)
        summaries.append({"candidate_id":candidate_id,"rr":rr,"feature":feature,"value":value,
                          "raw_rows":len(g),"purged_rows":len(gp),"market_specific":not general,
                          "bonferroni_z":z_standard,"required_samples":required,
                          "positive_stress_all_periods":positive_all,"adjusted_holdout_pass":adjusted_holdout,
                          "leave_one_market_out_pass":loo_pass,"survived_phase3f":survived,
                          **{f"{p}_{k}":v for p,m in periods.items() for k,v in m.items()}})
        print(f"{candidate_id}: purged={len(gp):,} survived={survived}", flush=True)

    summary = pd.DataFrame(summaries)
    summary.to_csv(out / "phase3f_candidate_summary.csv", index=False)
    pd.DataFrame(slice_rows).to_csv(out / "phase3f_stability_slices.csv", index=False)
    (out / "phase3f_leave_one_market_out.json").write_text(json.dumps(loo_json, indent=2, default=str), encoding="utf-8")
    survivors = summary[summary.survived_phase3f] if len(summary) else summary
    survivors.to_csv(out / "phase3f_survivors.csv", index=False)
    report = {"schema":"TP_CANONICAL_PHASE3F_FALSIFICATION_1","created_utc":datetime.now(timezone.utc).isoformat(),
              "reference_db":str(DB),"reference_integrity":integrity,"reference_rows":len(zones),
              "candidate_source":str(cpath),"input_candidates":len(candidates),"multiple_tests":TOTAL_TESTS,
              "correction":"Bonferroni one-sided Wilson lower bound","bonferroni_z":z_standard,
              "overlap_policy":"one highest OTA/profit-room setup per symbol per 240-minute cluster",
              "cost_model":{"commission_round_trip_usd":ROUND_TRIP_COMMISSION,"tick_value_usd":TICK_VALUE,
                            "base_slippage":"1 tick each side","stress_slippage":"2 ticks each side"},
              "minimum_samples":{"development":500,"calibration":150,"holdout":150},
              "survivors":len(survivors),"live_promotion":False,"integrity":"ok"}
    (out / "phase3f_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"OUTPUT READY: {out}")
    print(f"PHASE 3F SURVIVORS: {len(survivors)}/{len(candidates)}")
    print("LIVE PROMOTION: False")


if __name__ == "__main__":
    main()
