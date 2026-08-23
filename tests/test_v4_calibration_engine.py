import sys,sqlite3,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_calibration_engine import wilson,score_bucket,calibrate,CalibratedScorer
def test_bucket():
    assert score_bucket(8.7)=="8.5-8.9" and score_bucket(9.1)=="9+"
def test_wilson():
    lo,hi=wilson(50,100);assert 0<lo<.5<hi<1
def test_calibration():
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/"e.db";c=sqlite3.connect(p)
        c.execute("create table evidence(symbol text,setup_type text,direction text,score10 real,entered int,primary_hit int,stretch_hit int,alive_mfe_r real,alive_mae_r real)")
        for i in range(100):
            c.execute("insert into evidence values(?,?,?,?,?,?,?,?,?)",("GC","supply","SHORT",9.2,1,1 if i<70 else 0,1 if i<45 else 0,4,-.7))
        c.commit();c.close()
        r=calibrate(p,25);assert r["rows"]==100
        s=CalibratedScorer(r).score("GC","supply","SHORT",9.2)
        assert s["evidence_score10"] is not None and 0<=s["calibrated_score10"]<=10
