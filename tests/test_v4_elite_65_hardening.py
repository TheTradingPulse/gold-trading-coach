import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"core"))
from v4_elite_65_hardening import wilson,stats,rrbin,streak
def test_wilson():assert wilson(65,100)<.65
def test_rr():assert rrbin(3.5)=="3-4" and rrbin(5.2)=="5+"
def test_stats():assert stats([{"entered":1,"primary_hit":1}],3)["ev_r"]==3
def test_streak():assert streak([{"entered":1,"primary_hit":0},{"entered":1,"primary_hit":0},{"entered":1,"primary_hit":1}],3)==2
