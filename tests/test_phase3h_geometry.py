import unittest
import pandas as pd
from tools.run_phase3h_gc_geometry import geometry,replay

class Row:
    proximal=100.;distal=99.;direction="LONG";entry_ts=pd.Timestamp("2025-01-01",tz="UTC")

class GeometryTests(unittest.TestCase):
    def test_minimum_stop(self):
        e,s,r,t=geometry(Row(),{"entry_offset":0.,"stop_style":"MIN_RISK_TICKS","stop_value":20},pd.Series(dtype=float))
        self.assertAlmostEqual(t,20);self.assertAlmostEqual(s,98)
    def test_deeper_long_entry_requires_fill(self):
        e,s,r,t=geometry(Row(),{"entry_offset":.5,"stop_style":"ORIGINAL","stop_value":None},pd.Series(dtype=float))
        self.assertEqual(e,99.5);self.assertAlmostEqual(s,98.9)
    def test_same_minute_is_not_verified(self):
        idx=pd.date_range("2025-01-01",periods=2,freq="min",tz="UTC")
        fill,terminal,mv,mp=replay(idx,[104,100],[98,99],idx[0],"LONG",100,99,1)
        self.assertEqual(terminal,"stopped");self.assertEqual(mv,0);self.assertGreaterEqual(mp,4)

if __name__=="__main__":unittest.main()
