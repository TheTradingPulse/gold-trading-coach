import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_grandslam_oos_validator import split_rows,_metric,_ordered

def test_time_split():
    rows=[{"as_of":str(i)} for i in range(10)]
    a,b=split_rows(rows,.7)
    assert len(a)==7 and len(b)==3

def test_metric():
    rows=[
      {"entered":1,"primary_hit":1,"stretch_hit":1},
      {"entered":1,"primary_hit":1,"stretch_hit":0},
      {"entered":1,"primary_hit":0,"stretch_hit":0},
      {"entered":0,"primary_hit":0,"stretch_hit":0},
    ]
    m=_metric(rows)
    assert m["triggered"]==3 and m["hit_3r"]==2 and m["hit_5r"]==1
    assert m["realized_ev_3r"]==round((6-1)/3,4)

def test_ordering():
    s={t:{"triggered":30,"hit_3r_pct":v} for t,v in zip(["RESEARCH","WATCH","ELITE","GRAND_SLAM"],[30,40,60,80])}
    assert _ordered(s,"hit_3r_pct")
