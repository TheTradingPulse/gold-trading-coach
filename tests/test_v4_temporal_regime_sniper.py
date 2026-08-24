import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"core"))
from v4_temporal_regime_sniper import wilson_low,ev,choose_target,prune_redundant
def test_wilson_conservative(): assert 0 < wilson_low(60,100) < .60
def test_ev(): assert ev(.50,3)==1.0 and ev(.50,5)==2.0
def test_target_requires_incremental_edge():
    assert choose_target({"triggered":100,"ev3":1.1,"ev5":1.15,"w5":.5})=="3R"
    assert choose_target({"triggered":100,"ev3":1.1,"ev5":1.5,"w5":.4})=="5R"
def test_prune():
    r={"features":("a",),"values":("b",)}
    assert len(prune_redundant([r,r]))==1
