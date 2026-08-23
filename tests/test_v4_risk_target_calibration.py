import sys
from pathlib import Path
import pandas as pd
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/"core"))
from v4_risk_target_policy import planned_levels
from v4_outcome_engine import evaluate_outcome

def _df(highs,lows):
    idx=pd.date_range("2026-01-01",periods=len(highs),freq="15min",tz="UTC")
    return pd.DataFrame({"open":[100]*len(highs),"high":highs,"low":lows,
                         "close":[100]*len(highs),"volume":[1]*len(highs)},index=idx)

def test_long_3r_5r_geometry():
    p=planned_levels({"direction":"LONG","entry":100,"stop":98})
    assert p["primary_target"]==106 and p["stretch_target"]==110

def test_short_3r_5r_geometry():
    p=planned_levels({"direction":"SHORT","entry":100,"stop":102})
    assert p["primary_target"]==94 and p["stretch_target"]==90

def test_5r_hit_caps_realized_at_5():
    r=evaluate_outcome({"direction":"LONG","entry":100,"stop":99},_df([100,106],[100,100]))
    assert r["stretch_hit"] and r["realized_r"]==5.0 and r["achieved_r"]==5.0

def test_stop_caps_alive_mae_at_minus_one_but_preserves_raw():
    r=evaluate_outcome({"direction":"LONG","entry":100,"stop":99},_df([101],[80]))
    assert r["stop_hit"] and r["realized_r"]==-1.0
    assert r["alive_mae_r"]==-1.0
    assert r["raw_mae_r"]==-20.0

def test_same_bar_preserves_target_then_stop_contract_and_flags_ambiguity():
    r=evaluate_outcome({"direction":"LONG","entry":100,"stop":99},_df([104],[98]))
    assert r["primary_hit"] and r["outcome"]=="T1_THEN_STOP"
    assert r["same_bar_ambiguous"] and r["realized_r"]==-1.0


def test_legacy_geometry_and_research_targets_are_separate():
    f=_df([104,104],[100,100])
    r=evaluate_outcome({"direction":"LONG","entry":100,"stop":98,"t1":103},f)
    assert r["target_r"]["T1"]==1.5
    assert r["achieved_r"]==1.5
    assert r["research_target_r"]["PRIMARY_3R"]==3.0
    assert r["research_target_r"]["STRETCH_5R"]==5.0


def test_achieved_r_legacy_geometry_when_target_supplied():
    r=evaluate_outcome({"direction":"LONG","entry":100,"stop":98,"t1":103},_df([104,104],[100,100]))
    assert r["achieved_r"]==1.5
    assert r["research_achieved_r"]==0.0

def test_achieved_r_falls_back_to_research_when_no_legacy_targets():
    r=evaluate_outcome({"direction":"LONG","entry":100,"stop":99},_df([100,106],[100,100]))
    assert r["stretch_hit"]
    assert r["realized_r"]==5.0
    assert r["research_achieved_r"]==5.0
    assert r["achieved_r"]==5.0
