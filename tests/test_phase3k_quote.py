import importlib.util
import unittest
from pathlib import Path


class QuoteSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path("tools/run_phase3k_micro_5y_quote.py")
        cls.text = path.read_text(encoding="utf-8")
        spec = importlib.util.spec_from_file_location("phase3k_quote", path)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_fixed_micro_basket(self):
        self.assertEqual(
            self.module.MICROS,
            ("MGC", "SIL", "MES", "MNQ", "MYM", "M2K", "MCL", "MNG"),
        )

    def test_fixed_five_year_period(self):
        self.assertEqual(self.module.START, "2021-01-01T00:00:00Z")
        self.assertEqual(self.module.END, "2026-01-01T00:00:00Z")

    def test_quote_request_matches_installed_sdk(self):
        request = self.module.quote_request("MES")
        self.assertEqual(request["schema"], "ohlcv-1m")
        self.assertEqual(request["symbols"], "MES.v.0")
        self.assertEqual(request["stype_in"], "continuous")
        self.assertNotIn("stype_out", request)

    def test_no_download_api_or_approval_flag(self):
        self.assertNotIn("timeseries.get_range", self.text)
        self.assertNotIn("approve", self.text.lower())


if __name__ == "__main__":
    unittest.main()
