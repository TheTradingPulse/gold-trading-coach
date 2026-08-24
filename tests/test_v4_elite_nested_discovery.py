import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_elite_nested_discovery import split4,outcome_stats,_wilson
def test_split4():
 r=[{"x":i} for i in range(100)];a,b,c,d=split4(r);assert [len(x) for x in (a,b,c,d)]==[50,20,15,15]
def test_stats():
 r=[{"entered":1,"primary_hit":1,"stretch_hit":1},{"entered":1,"primary_hit":0,"stretch_hit":0}]
 s=outcome_stats(r);assert s["triggered"]==2 and s["p3"]==.5 and s["ev3"]==1
def test_wilson_conservative():
 assert _wilson(8,10)<.8 and _wilson(800,1000)<.8
