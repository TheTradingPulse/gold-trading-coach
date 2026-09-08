import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from trade_quality_contract import TradeProposal, decision_time_chart_levels, evaluate_trade_quality


def proposal(**overrides):
    values = dict(
        setup_family="TREND_CONTINUATION", direction="LONG",
        decision_ts="2026-09-08T14:15:00Z", entry=3600.0, stop=3597.0,
        target_r=3, risk_dollars=300.0, room_r=4.2, trend_4h="BULLISH",
        location_valid=True, displacement=True, confirmation_close=True,
        structure_break_15m=True, pullback_valid=True,
    )
    values.update(overrides)
    return TradeProposal(**values)


class TradeQualityContractTests(unittest.TestCase):
    def test_valid_trend_continuation_is_ready(self):
        result = evaluate_trade_quality(proposal())
        self.assertEqual(result.status, "READY")
        self.assertEqual(result.t1, 3609.0)
        self.assertEqual(result.t2, 3609.0)

    def test_countertrend_first_touch_is_rejected(self):
        result = evaluate_trade_quality(proposal(trend_4h="BEARISH", structure_break_15m=False))
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("COUNTERTREND_CONTINUATION", result.rejection_reasons)
        self.assertIn("NO_15M_CONTINUATION_BREAK", result.rejection_reasons)
        self.assertIsNone(decision_time_chart_levels(result))

    def test_five_r_requires_five_r_of_clear_room(self):
        result = evaluate_trade_quality(proposal(target_r=5, room_r=4.9))
        self.assertIn("INSUFFICIENT_CLEAR_PROFIT_ROOM", result.rejection_reasons)

    def test_risk_is_a_ceiling_not_a_target(self):
        self.assertEqual(evaluate_trade_quality(proposal(risk_dollars=85)).status, "READY")
        self.assertEqual(
            evaluate_trade_quality(proposal(risk_dollars=300.01)).status,
            "REJECTED",
        )

    def test_confirmed_countertrend_reversal_can_qualify(self):
        result = evaluate_trade_quality(proposal(
            setup_family="LIQUIDITY_SWEEP_REVERSAL", trend_4h="BEARISH",
            pullback_valid=False, liquidity_sweep=True, reclaim_confirmed=True,
        ))
        self.assertEqual(result.status, "READY")

    def test_ready_chart_has_only_entry_stop_t1_t2_after_decision(self):
        result = evaluate_trade_quality(proposal(target_r=5, room_r=6))
        levels = decision_time_chart_levels(result)
        self.assertEqual(set(levels), {"start_ts", "Entry", "Stop", "T1", "T2"})
        self.assertEqual(levels["start_ts"], result.decision_ts)
        self.assertEqual(levels["T1"], 3609.0)
        self.assertEqual(levels["T2"], 3615.0)


if __name__ == "__main__":
    unittest.main()
