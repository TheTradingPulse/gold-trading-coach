import sys,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_calibrated_policy import V4CalibratedPolicy
def _report(q=7.0,trig=50):
    return {"groups":[{"symbol":"GC","setup_type":"demand","direction":"LONG","bucket":"9+",
    "sample_ok":True,"triggered":trig,"evidence_quality10":q,"hit_3r_pct":70,"hit_5r_pct":50,
    "avg_mfe_r":4,"avg_mae_r":-.8}]}
def test_evidence_can_create_elite(tmp_path):
    p=tmp_path/"c.json";p.write_text(json.dumps(_report()))
    r=V4CalibratedPolicy(p).classify({"symbol":"GC","setup_type":"demand","direction":"LONG","score10":9.5})
    assert r["tier"]=="ELITE"
def test_raw_nine_not_enough(tmp_path):
    p=tmp_path/"c.json";p.write_text(json.dumps({"groups":[]}))
    r=V4CalibratedPolicy(p).classify({"symbol":"GC","setup_type":"demand","direction":"LONG","score10":9.9})
    assert r["tier"]=="INSUFFICIENT_EVIDENCE"
def test_weak_evidence_blocks_elite(tmp_path):
    p=tmp_path/"c.json";p.write_text(json.dumps(_report(3.0,100)))
    r=V4CalibratedPolicy(p).classify({"symbol":"GC","setup_type":"demand","direction":"LONG","score10":9.9})
    assert r["tier"]=="RESEARCH"
