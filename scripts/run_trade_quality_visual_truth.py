#!/usr/bin/env python3
"""Build an outcome-blind 3R/5R visual truth set from frozen candidates.

Candidate rows must contain only features known at ``decision_ts``.  Outcome
bars are loaded separately and are never passed into the quality contract.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from trade_quality_contract import (  # noqa: E402
    ALLOWED_TARGET_R,
    TradeProposal,
    decision_time_chart_levels,
    evaluate_trade_quality,
)


REQUIRED_CANDIDATE_COLUMNS = {
    "candidate_id", "setup_family", "direction", "decision_ts", "entry", "stop",
    "risk_dollars", "room_r", "trend_4h", "location_valid", "displacement",
    "confirmation_close", "structure_break_15m",
}


def _bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def load_bars(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path) if path.suffix.lower() in {".parquet", ".pq"} else pd.read_csv(path)
    columns = {str(c).lower(): c for c in frame.columns}
    time_col = next((columns[k] for k in ("timestamp", "ts_event", "datetime", "time") if k in columns), None)
    if time_col is None:
        raise ValueError("Bars require timestamp/ts_event/datetime/time")
    frame.index = pd.to_datetime(frame[time_col], utc=True, errors="coerce")
    frame = frame.rename(columns={columns[k]: k for k in ("open", "high", "low", "close") if k in columns})
    missing = {"open", "high", "low", "close"} - set(frame.columns)
    if missing:
        raise ValueError(f"Bars missing columns: {sorted(missing)}")
    return frame.loc[~frame.index.isna(), ["open", "high", "low", "close"]].astype(float).sort_index()


def resolve_outcome(decision, bars: pd.DataFrame) -> tuple[str, str | None]:
    """Resolve stop versus selected target on exact lower-timeframe bars."""
    start = pd.Timestamp(decision.decision_ts)
    if start.tzinfo is None:
        start = start.tz_localize("UTC")
    future = bars[bars.index > start]
    for ts, bar in future.iterrows():
        if decision.direction == "LONG":
            stop_hit = bar.low <= decision.stop
            target_hit = bar.high >= decision.t2
        else:
            stop_hit = bar.high >= decision.stop
            target_hit = bar.low <= decision.t2
        if stop_hit and target_hit:
            return "AMBIGUOUS_SAME_BAR", ts.isoformat()
        if stop_hit:
            return "STOP_FIRST", ts.isoformat()
        if target_hit:
            return f"TARGET_{decision.target_r}R_FIRST", ts.isoformat()
    return "UNRESOLVED", None


def proposal_from_row(row: pd.Series, target_r: int) -> TradeProposal:
    optional = {
        name: _bool(row.get(name, False))
        for name in (
            "pullback_valid", "breakout_confirmed", "retest_confirmed",
            "liquidity_sweep", "reclaim_confirmed", "opposing_structure_clear",
        )
    }
    if "opposing_structure_clear" not in row.index:
        optional["opposing_structure_clear"] = True
    return TradeProposal(
        setup_family=str(row.setup_family), direction=str(row.direction),
        decision_ts=str(row.decision_ts), entry=float(row.entry), stop=float(row.stop),
        target_r=target_r, risk_dollars=float(row.risk_dollars), room_r=float(row.room_r),
        trend_4h=str(row.trend_4h), location_valid=_bool(row.location_valid),
        displacement=_bool(row.displacement), confirmation_close=_bool(row.confirmation_close),
        structure_break_15m=_bool(row.structure_break_15m), **optional,
    )


def audit(candidates: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_CANDIDATE_COLUMNS - set(candidates.columns)
    if missing:
        raise ValueError(f"Candidates missing columns: {sorted(missing)}")
    rows = []
    for _, candidate in candidates.iterrows():
        for target_r in ALLOWED_TARGET_R:
            decision = evaluate_trade_quality(proposal_from_row(candidate, target_r))
            outcome, outcome_ts = (resolve_outcome(decision, bars) if decision.status == "READY" else ("NOT_EXECUTED", None))
            rows.append({
                "candidate_id": candidate.candidate_id,
                **decision.to_dict(),
                "chart_levels": json.dumps(decision_time_chart_levels(decision)),
                "outcome": outcome,
                "outcome_ts": outcome_ts,
            })
    return pd.DataFrame(rows)


def build_report(results: pd.DataFrame) -> dict:
    report = {
        "schema": "TP_VISUAL_TRUTH_3R5R_1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "integrity": "outcome_blind_decision_contract_then_exact_bar_replay_fail_closed",
        "targets": {},
    }
    for target_r in ALLOWED_TARGET_R:
        sample = results[results.target_r == target_r]
        ready = sample[sample.status == "READY"]
        resolved = ready[ready.outcome.isin(["STOP_FIRST", f"TARGET_{target_r}R_FIRST"])]
        wins = int((resolved.outcome == f"TARGET_{target_r}R_FIRST").sum())
        losses = int((resolved.outcome == "STOP_FIRST").sum())
        rate = wins / len(resolved) if len(resolved) else None
        report["targets"][f"{target_r}R"] = {
            "candidates": int(len(sample)), "ready": int(len(ready)),
            "rejected": int((sample.status == "REJECTED").sum()),
            "resolved": int(len(resolved)), "wins": wins, "losses": losses,
            "ambiguous": int((ready.outcome == "AMBIGUOUS_SAME_BAR").sum()),
            "win_rate": rate,
            "gross_expectancy_r": None if rate is None else rate * target_r - (1.0 - rate),
        }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--bars", type=Path, required=True, help="Exact 1m bars preferred")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    candidates = pd.read_csv(args.candidates)
    bars = load_bars(args.bars)
    results = audit(candidates, bars)
    results.to_csv(args.output / "trade_quality_decisions.csv", index=False)
    report = build_report(results)
    (args.output / "trade_quality_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
