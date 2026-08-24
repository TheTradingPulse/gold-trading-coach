import importlib.util
import unittest
from pathlib import Path

import pandas as pd


class DiamondLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path("tools/run_phase3l_overnight_diamond_lab.py")
        cls.text = path.read_text(encoding="utf-8")
        spec = importlib.util.spec_from_file_location("diamond_lab", path)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_market_mapping_and_rr_ladder(self):
        self.assertEqual(len(self.module.MARKETS), 8)
        self.assertEqual(self.module.MARKETS["GC"]["micro"], "MGC")
        self.assertEqual(self.module.MARKETS["RTY"]["micro"], "M2K")
        self.assertEqual(self.module.RR_TARGETS, tuple(range(1, 21)))

    def test_no_network_or_live_mutation(self):
        lowered = self.text.lower()
        self.assertNotIn("databento", lowered)
        self.assertNotIn("requests.", lowered)
        self.assertNotIn("urllib", lowered)
        self.assertNotIn("delete from", lowered)
        self.assertNotIn("update professional_zones", lowered)

    def test_fail_closed_same_bar_replay(self):
        idx = pd.date_range("2025-01-01", periods=3, freq="min", tz="UTC")
        high = [100.0, 103.0, 103.0]
        low = [100.0, 97.0, 97.0]
        result = self.module.replay_micro(idx, high, low, idx[0], "LONG", 100.0, 98.0, 2.0)
        self.assertEqual(result[2], 0)
        self.assertGreaterEqual(result[3], 1)

    def test_material_improvement_threshold(self):
        self.assertGreaterEqual(self.module.MIN_MATERIAL_NET_R, 0.05)
        self.assertGreaterEqual(self.module.MIN_SAFE_RISK_USD, 75.0)

    def test_result_package_excludes_checkpoints_and_parquet(self):
        packager = Path("tools/package_phase3l_result.py").read_text(encoding="utf-8")
        self.assertIn('ALLOWED = {".json", ".csv", ".txt", ".log"}', packager)
        self.assertNotIn('".parquet"', packager)


if __name__ == "__main__":
    unittest.main()
