import json,unittest
from pathlib import Path

class FrozenTests(unittest.TestCase):
    def test_hypothesis_is_exact(self):
        p=Path("config/phase3i_frozen_hypothesis.json");x=json.loads(p.read_text())
        self.assertEqual(x["stop"],"max(original structural stop, 1.0 x point-in-time 5-minute ATR14)")
        self.assertEqual(x["target"],"5R");self.assertFalse(x["parameter_search_allowed"])
    def test_confirmation_dates_are_fixed(self):
        x=json.loads(Path("config/phase3i_frozen_hypothesis.json").read_text())
        self.assertEqual(x["confirmation_start"],"2026-01-01T00:00:00Z")
        self.assertEqual(x["confirmation_end_exclusive"],"2026-08-23T19:00:00Z")
    def test_databento_continuous_is_input_only(self):
        runner=Path("tools/run_phase3i_frozen_gc_confirmation.py").read_text(encoding="utf-8")
        self.assertIn('stype_in="continuous"',runner)
        self.assertIn('stype_out="instrument_id"',runner)
        self.assertNotIn('stype_out="continuous"',runner)

if __name__=="__main__":unittest.main()
