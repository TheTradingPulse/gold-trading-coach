import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from trade_setup_detector import _trend_4h, detect_trade_setups


def bars(closes, freq="15min"):
    closes = np.asarray(closes, dtype=float)
    index = pd.date_range("2026-01-01", periods=len(closes), freq=freq, tz="UTC")
    return pd.DataFrame({
        "open": closes - 0.15,
        "high": closes + 0.35,
        "low": closes - 0.35,
        "close": closes,
        "volume": 100,
    }, index=index)


class TradeSetupDetectorTests(unittest.TestCase):
    def test_recent_structure_break_overrides_lagging_ema(self):
        h4 = bars(np.r_[np.linspace(100, 110, 24), 96], "4h")
        prepared = __import__("trade_setup_detector")._prepare(h4)
        self.assertEqual(_trend_4h(prepared), "BEARISH")

    def test_detector_never_emits_outcome_columns(self):
        m15 = bars(np.linspace(100, 115, 80))
        h4 = bars(np.linspace(90, 120, 30), "4h")
        result = detect_trade_setups(m15, h4)
        self.assertFalse({"outcome", "win", "mfe_r", "mae_r"} & set(result.columns))

    def test_flat_noise_does_not_create_a_trade(self):
        m15 = bars(np.full(80, 100.0))
        h4 = bars(np.full(30, 100.0), "4h")
        self.assertTrue(detect_trade_setups(m15, h4).empty)


if __name__ == "__main__":
    unittest.main()
