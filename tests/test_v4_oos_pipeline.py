import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"core"))
from v4_candidate_intelligence import enrich_candidate
from v4_oos_validation import tier_for
def test_tier_gate():
    assert tier_for(None)=="INSUFFICIENT_EVIDENCE"
    assert tier_for({"evidence_quality10":7,"triggered":50})=="ELITE"
    assert tier_for({"evidence_quality10":4.5,"triggered":30})=="WATCH"
    assert tier_for({"evidence_quality10":3,"triggered":100})=="RESEARCH"
def test_pipeline_existing_calibration():
    p=Path("research_data/v4/v4_calibration.json")
    if p.exists():
        r=enrich_candidate({"symbol":"GC","setup_type":"demand","direction":"LONG","score10":9.3})
        assert "v4_scoring" in r and "professor_chart_context" in r
        assert r["live_v3_4_untouched"] is True
