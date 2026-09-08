#!/usr/bin/env python3
"""End-to-end Gold replay for the canonical three-setup detector."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "scripts"))

from trade_setup_detector import detect_trade_setups  # noqa: E402
from run_trade_quality_visual_truth import audit, build_report, load_bars  # noqa: E402


def resample(frame, rule):
    return frame.resample(rule, label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gc-1m", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    one = load_bars(args.gc_1m)
    candidates = detect_trade_setups(resample(one, "15min"), resample(one, "4h"))
    candidate_path = args.output / "gc_three_setup_candidates.csv"
    candidates.to_csv(candidate_path, index=False)
    if candidates.empty:
        report = {
            "schema": "TP_GC_THREE_SETUP_REPLAY_1",
            "candidates": 0,
            "message": "No causal candidates met the frozen detector rules.",
        }
        (args.output / "trade_quality_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0

    decisions = audit(candidates, one)
    decisions.to_csv(args.output / "trade_quality_decisions.csv", index=False)
    report = build_report(decisions)
    report["schema"] = "TP_GC_THREE_SETUP_REPLAY_1"
    report["candidate_families"] = candidates.setup_family.value_counts().to_dict()
    (args.output / "trade_quality_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
