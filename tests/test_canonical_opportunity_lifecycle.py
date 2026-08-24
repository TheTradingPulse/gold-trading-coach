import unittest
import pandas as pd

from core.canonical_opportunity_lifecycle import classify_zone


def bars(rows):
    return pd.DataFrame(rows, index=pd.date_range("2026-01-01", periods=len(rows), freq="5min", tz="UTC"))


class LifecycleTests(unittest.TestCase):
    def zone(self, direction="LONG"):
        return {"direction": direction, "entry": 100.0, "stop": 99.0 if direction == "LONG" else 101.0,
                "risk": 1.0, "entry_ts": "2026-01-01T00:00:00Z"}

    def test_target_before_stop(self):
        x = bars([{"high":101,"low":99.5,"close":100.5},{"high":105,"low":100,"close":104}])
        self.assertEqual(classify_zone(self.zone(), x)["state"], "RESOLVED_TARGET")

    def test_short_stop(self):
        x = bars([{"high":100.5,"low":99,"close":99.5},{"high":101.2,"low":99,"close":101}])
        self.assertEqual(classify_zone(self.zone("SHORT"), x)["state"], "RESOLVED_STOP")

    def test_same_bar_is_fail_closed(self):
        x = bars([{"high":106,"low":98,"close":100}])
        result = classify_zone(self.zone(), x)
        self.assertEqual(result["state"], "SAME_BAR_AMBIGUOUS")
        self.assertFalse(result["dashboard_eligible"])

    def test_managing(self):
        x = bars([{"high":101.5,"low":99.5,"close":101.1}])
        self.assertEqual(classify_zone(self.zone(), x)["state"], "MANAGING")

    def test_expired(self):
        x = bars([{"high":100.5,"low":99.5,"close":100}] * 4)
        self.assertEqual(classify_zone(self.zone(), x, max_active_bars=3)["state"], "EXPIRED")


if __name__ == "__main__":
    unittest.main()
