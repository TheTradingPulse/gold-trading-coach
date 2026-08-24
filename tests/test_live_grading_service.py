import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from live_grading_service import has_live_star


class LiveGradingServiceTests(unittest.TestCase):
    def test_star_requires_explicit_eligibility(self):
        self.assertFalse(has_live_star({"tier": "V4 ELITE", "live_eligible": False}))

    def test_non_elite_never_has_star(self):
        self.assertFalse(has_live_star({"tier": "EVIDENCE MATCH", "live_eligible": True}))

    def test_verified_elite_can_have_star(self):
        self.assertTrue(has_live_star({"tier": "V4 ELITE", "live_eligible": True}))


if __name__ == "__main__":
    unittest.main()
