"""V3.4E shared opportunity policy helpers for live/research parity.

The historical adapter can use these pure functions without changing live rules.
No database or network side effects exist in this module.
"""
from __future__ import annotations

ELITE_MIN_SCORE=90.0
WATCH_MIN_SCORE=85.0
ACTIVE_LIFECYCLES={"APPROACHING","IN_ZONE","QUALIFIED"}
STRUCTURAL_TIMEFRAMES={"D","4H","1H","15m"}
CONFIRMATION_TIMEFRAMES={"5m","1m"}
RR_MIN=2.0
RR_MAX=50.0
ZONE_QUALITY_MIN=75.0
FRESHNESS_MIN=70.0
MAX_RETESTS=1
MIN_MTF_RATIO=0.40

def classify_fields(*, score, lifecycle, timeframe, zone_quality, freshness,
                    retests, projected_rr, mtf_total=0, mtf_ratio=0.0):
    """Pure classification gate used for validation and future replay integration."""
    if float(score)<WATCH_MIN_SCORE:return "REJECT","score_below_8_5"
    if str(lifecycle).upper() not in ACTIVE_LIFECYCLES:return "REJECT","inactive_lifecycle"
    if str(timeframe) not in STRUCTURAL_TIMEFRAMES:
        return "REJECT",("confirmation_timeframe_only" if str(timeframe) in CONFIRMATION_TIMEFRAMES else "timeframe_excluded")
    if float(zone_quality)<ZONE_QUALITY_MIN:return "REJECT","zone_quality_below_75"
    if float(freshness)<FRESHNESS_MIN:return "REJECT","freshness_below_70"
    if int(retests)>MAX_RETESTS:return "REJECT","too_many_retests"
    if projected_rr is None:return "REJECT","rr_unavailable"
    if float(projected_rr)<RR_MIN:return "REJECT","rr_below_2"
    if float(projected_rr)>RR_MAX:return "REJECT","rr_implausible_above_50"
    if int(mtf_total)>=3 and float(mtf_ratio)<MIN_MTF_RATIO:return "REJECT","mtf_below_40pct"
    return ("ELITE","qualified") if float(score)>=ELITE_MIN_SCORE else ("WATCH","qualified")
