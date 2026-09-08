import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_trade_quality_visual_truth import audit, build_report


class VisualTruthRunnerTests(unittest.TestCase):
    def test_three_and_five_r_are_resolved_independently(self):
        candidate = pd.DataFrame([{
            "candidate_id": "good-long", "setup_family": "TREND_CONTINUATION",
            "direction": "LONG", "decision_ts": "2026-01-01T10:00:00Z",
            "entry": 100.0, "stop": 99.0, "risk_dollars": 100.0, "room_r": 6.0,
            "trend_4h": "BULLISH", "location_valid": True, "displacement": True,
            "confirmation_close": True, "structure_break_15m": True,
            "pullback_valid": True,
        }])
        bars = pd.DataFrame(
            {"open": [100, 103, 105], "high": [102, 104.2, 105.2],
             "low": [99.5, 102, 104], "close": [101, 104, 105]},
            index=pd.to_datetime(["2026-01-01T10:01Z", "2026-01-01T10:02Z", "2026-01-01T10:03Z"]),
        )
        result = audit(candidate, bars)
        self.assertEqual(result.loc[result.target_r == 3, "outcome"].iloc[0], "TARGET_3R_FIRST")
        self.assertEqual(result.loc[result.target_r == 5, "outcome"].iloc[0], "TARGET_5R_FIRST")
        report = build_report(result)
        self.assertEqual(report["targets"]["3R"]["win_rate"], 1.0)
        self.assertEqual(report["targets"]["5R"]["gross_expectancy_r"], 5.0)

    def test_rejected_candidate_never_uses_future_outcome(self):
        candidate = pd.DataFrame([{
            "candidate_id": "bad-long", "setup_family": "TREND_CONTINUATION",
            "direction": "LONG", "decision_ts": "2026-01-01T10:00:00Z",
            "entry": 100.0, "stop": 99.0, "risk_dollars": 100.0, "room_r": 6.0,
            "trend_4h": "BEARISH", "location_valid": True, "displacement": True,
            "confirmation_close": True, "structure_break_15m": False,
            "pullback_valid": False,
        }])
        bars = pd.DataFrame({"open":[100],"high":[110],"low":[100],"close":[109]},
                            index=pd.to_datetime(["2026-01-01T10:01Z"]))
        result = audit(candidate, bars)
        self.assertTrue((result.outcome == "NOT_EXECUTED").all())


if __name__ == "__main__":
    unittest.main()
