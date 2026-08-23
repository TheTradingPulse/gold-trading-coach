import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_sniper_features import extract
from v4_sniper_policy import decide
from v4_target_manager import target_plan
def test_missing_context_not_invented():
    f=extract({"symbol":"GC","setup_type":"demand","direction":"LONG","entry":100,"stop":99})
    assert f["trend_regime"] is None and f["risk_points"]==1
def test_small_sample_blocked():
    assert decide({"triggered":20,"hit_3r":20,"hit_5r":20})["tier"]=="INSUFFICIENT_EVIDENCE"
def test_target_runner_margin():
    p=target_plan({"ev_3r":1.0,"ev_5r":1.3});assert p["mode"]=="3R_PLUS_5R_RUNNER"
    p=target_plan({"ev_3r":1.0,"ev_5r":1.05});assert p["mode"]=="FIXED_3R"
