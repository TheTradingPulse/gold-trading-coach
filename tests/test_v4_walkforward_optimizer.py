import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_walkforward_optimizer import _expected_r,_tier,_blend
def test_expected_r():
    assert round(_expected_r({"hit_3r_pct":50},3),2)==1.0
    assert round(_expected_r({"hit_5r_pct":50},5),2)==2.0
def test_strict_tiers():
    assert _tier(3,20,0)=="INSUFFICIENT_EVIDENCE"
    assert _tier(2,60,.2)=="ELITE"
    assert _tier(.9,40,.1)=="WATCH"
    assert _tier(.1,100,.2)=="RESEARCH"
def test_shrinkage():
    x={"triggered":10,"hit_3r_pct":100,"hit_5r_pct":100}
    p={"triggered":500,"hit_3r_pct":40,"hit_5r_pct":25}
    b=_blend(x,p,p,p)
    assert b and b["edge"] < _expected_r(x,5)
