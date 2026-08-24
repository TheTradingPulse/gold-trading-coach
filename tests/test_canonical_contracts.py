import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"core"))
from canonical_contracts import CanonicalOutcome, CanonicalSetup, EvidenceDecision


class ContractTests(unittest.TestCase):
    def test_valid_long(self):
        x=CanonicalSetup("x","test","1","GC","LONG","RBR","5m",None,None,100,99,1,9.5)
        self.assertEqual(x.validate(),[])
    def test_bad_stop(self):
        x=CanonicalSetup("x","test","1","GC","LONG","RBR","5m",None,None,100,101,1,9.5)
        self.assertIn("long_stop_not_below_entry",x.validate())
    def test_verified_cannot_exceed_possible(self):
        x=CanonicalOutcome("x","1",5,4)
        self.assertIn("verified_exceeds_possible",x.validate())
    def test_rr_ladder(self):
        x=CanonicalOutcome("x","1",7.2,9)
        self.assertTrue(x.verified_hit(7));self.assertFalse(x.verified_hit(8))
    def test_elite_requires_execution(self):
        x=EvidenceDecision("x","1","ELITE",9.5,7.0,100,5,False,"test")
        self.assertFalse(x.live_eligible())


if __name__=="__main__": unittest.main()
