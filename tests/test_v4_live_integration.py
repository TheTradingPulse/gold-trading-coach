import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from v4_live_integration import classify_live_candidate, v4_system_status


class Candidate:
    zone_type = "demand"
    setup_score = 99.0
    timeframe = "1H"
    lifecycle = "APPROACHING"
    zone_quality_score = 99.0
    freshness_score = 99.0
    retest_count = 0
    projected_rr = 5.0


def test_missing_release_bundle_fails_closed():
    result = classify_live_candidate(Candidate(), "GC")
    if not v4_system_status()["ready"]:
        assert result["tier"] == "INSUFFICIENT EVIDENCE"
        assert not result["release_ready"]


def test_structure_score_never_disappears():
    result = classify_live_candidate(Candidate(), "GC")
    assert result["structure_score10"] == 9.9


def test_promoted_gc_rule_remains_execution_unverified():
    if v4_system_status()["ready"]:
        result = classify_live_candidate(Candidate(), "GC")
        assert result["tier"] == "EVIDENCE MATCH"
        assert result["execution_status"] == "UNVERIFIED"
        assert result["triggered_sample"] >= 35


def test_raw_score_without_promoted_rule_is_not_elite():
    candidate = Candidate()
    candidate.zone_type = "supply"
    candidate.projected_rr = 1.5
    result = classify_live_candidate(candidate, "GC")
    assert result["tier"] != "ELITE"
