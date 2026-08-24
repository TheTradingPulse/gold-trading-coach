import unittest
import pandas as pd
from tools.run_canonical_phase3f_falsification import metric, purge_entries


class Phase3FTests(unittest.TestCase):
    def test_cost_adjusted_metric(self):
        x = pd.DataFrame({"max_verified_r":[3,0],"max_possible_r":[3,0],
                          "terminal":["stopped","stopped"],"cost_r_base":[.05,.05],
                          "cost_r_stress":[.10,.10]})
        m = metric(x, 3)
        self.assertAlmostEqual(m["net_expectancy_r"], .95)
        self.assertAlmostEqual(m["stress_expectancy_r"], .90)

    def test_ambiguity_is_not_win(self):
        x = pd.DataFrame({"max_verified_r":[0],"max_possible_r":[3],"terminal":["stopped"],
                          "cost_r_base":[.05],"cost_r_stress":[.10]})
        m = metric(x, 3)
        self.assertEqual(m["wins"], 0)
        self.assertEqual(m["ambiguous"], 1)

    def test_overlap_purge_prefers_known_score(self):
        ts = pd.to_datetime(["2025-01-01T00:00Z","2025-01-01T01:00Z","2025-01-01T08:00Z"])
        x = pd.DataFrame({"symbol":["GC"]*3,"entry_ts":ts,"ota_score":[7,9,8],"profit_room_r":[5,4,6]})
        y = purge_entries(x, 240)
        self.assertEqual(len(y), 2)
        self.assertIn(9, y.ota_score.tolist())


if __name__ == "__main__":
    unittest.main()
