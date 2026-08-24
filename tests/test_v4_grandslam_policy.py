import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'core'))
from v4_grandslam_policy import decide_grandslam

def test_raw_score_cannot_create_grandslam():
    r=decide_grandslam({'triggered':39,'hit_3r':39,'hit_5r':39},completeness=1,mean_similarity=1,projected_rr=10,actionable=True)
    assert r['tier']=='INSUFFICIENT_EVIDENCE'

def test_grandslam_requires_both_3r_and_5r_strength():
    r=decide_grandslam({'triggered':200,'hit_3r':180,'hit_5r':165},completeness=.9,mean_similarity=.9,projected_rr=8,actionable=True)
    assert r['tier']=='GRAND_SLAM'
    r=decide_grandslam({'triggered':200,'hit_3r':180,'hit_5r':60},completeness=.9,mean_similarity=.9,projected_rr=8,actionable=True)
    assert r['tier']!='GRAND_SLAM'

def test_grandslam_blocked_by_structure_or_actionability():
    s={'triggered':200,'hit_3r':180,'hit_5r':165}
    assert decide_grandslam(s,completeness=.9,mean_similarity=.9,projected_rr=2.2,actionable=True)['tier']!='GRAND_SLAM'
    assert decide_grandslam(s,completeness=.9,mean_similarity=.9,projected_rr=8,actionable=False)['tier']!='GRAND_SLAM'

def test_elite_is_still_strict():
    r=decide_grandslam({'triggered':150,'hit_3r':100,'hit_5r':65},completeness=.85,mean_similarity=.82,projected_rr=4,actionable=True)
    assert r['tier'] in {'ELITE','GRAND_SLAM'}
