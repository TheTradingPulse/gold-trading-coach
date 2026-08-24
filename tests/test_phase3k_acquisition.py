import importlib.util
import unittest
from pathlib import Path


class AcquisitionSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path("tools/run_phase3k_micro_5y_acquisition.py")
        cls.text = path.read_text(encoding="utf-8")
        spec = importlib.util.spec_from_file_location("phase3k_acquire", path)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_fixed_basket_and_period(self):
        self.assertEqual(self.module.MICROS, ("MGC", "SIL", "MES", "MNQ", "MYM", "M2K", "MCL", "MNG"))
        self.assertEqual(self.module.START, "2021-01-01T00:00:00Z")
        self.assertEqual(self.module.END, "2026-01-01T00:00:00Z")

    def test_quote_and_download_sdk_parameters(self):
        quote = self.module.quote_request("MGC")
        download = self.module.download_request("MGC")
        self.assertNotIn("stype_out", quote)
        self.assertEqual(download["stype_out"], "instrument_id")
        self.assertEqual(quote["symbols"], "MGC.v.0")

    def test_approval_cap_disk_and_atomic_guards(self):
        self.assertIn("if not approve_purchase:", self.text)
        self.assertIn("if total_cost > max_cost_usd:", self.text)
        self.assertIn("MIN_FREE_BYTES", self.text)
        self.assertIn(".partial.parquet", self.text)


if __name__ == "__main__":
    unittest.main()
