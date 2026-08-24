import ast
import importlib.util
import unittest
from pathlib import Path


class AcquisitionSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner_path = Path("tools/run_phase3j_data_acquisition.py")
        cls.runner = cls.runner_path.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.runner)
        spec = importlib.util.spec_from_file_location("phase3j_runner", cls.runner_path)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_contract_baskets_are_fixed(self):
        self.assertIn('STANDARD = ("SI", "ES", "NQ", "YM", "RTY", "CL", "NG")', self.runner)
        self.assertIn('MICRO = ("MGC", "SIL", "MES", "MNQ", "MYM", "M2K", "MCL", "MNG")', self.runner)

    def test_supported_symbology(self):
        quote = self.module.quote_request("ES")
        download = self.module.download_request("ES")
        self.assertEqual(quote["stype_in"], "continuous")
        self.assertNotIn("stype_out", quote)
        self.assertEqual(download["stype_out"], "instrument_id")
        self.assertNotIn('"stype_out": "continuous"', self.runner)

    def test_quote_and_download_parameter_sets_are_separate(self):
        quote = self.module.quote_request("MGC")
        download = self.module.download_request("MGC")
        self.assertEqual(quote["symbols"], "MGC.v.0")
        self.assertEqual(download["symbols"], "MGC.v.0")
        self.assertNotEqual(quote, download)

    def test_purchase_requires_approval_and_cap(self):
        self.assertIn("if not approve_core:", self.runner)
        self.assertIn("if total_cost > max_cost_usd:", self.runner)
        self.assertIn('action="store_true"', self.runner)


if __name__ == "__main__":
    unittest.main()
