from __future__ import annotations
import json
from pathlib import Path
from v4_calibration_engine import CalibratedScorer

DEFAULT_CALIBRATION = Path("research_data/v4/v4_calibration.json")

class V4CalibratedPolicy:
    """Research-only V4 policy. Does not mutate V3.4 live policy."""
    def __init__(self, calibration_path=DEFAULT_CALIBRATION):
        self.path=Path(calibration_path)
        if not self.path.exists():
            raise RuntimeError(f"Calibration file not found: {self.path}")
        self.report=json.loads(self.path.read_text(encoding="utf-8"))
        self.scorer=CalibratedScorer(self.report)

    def classify(self, candidate):
        def get(*names, default=None):
            for n in names:
                if isinstance(candidate,dict) and n in candidate:return candidate[n]
                if hasattr(candidate,n):return getattr(candidate,n)
            return default
        symbol=str(get("symbol",default="")).upper()
        setup=str(get("setup_type","zone_type","type",default="UNKNOWN")).lower()
        direction=str(get("direction","side",default="UNKNOWN")).upper()
        raw=get("score10","display_score","setup_score","score",default=0)
        raw=float(raw or 0)
        if raw>10: raw/=10.0
        r=self.scorer.score(symbol,setup,direction,raw)
        g=r.get("evidence_group")
        triggered=int((g or {}).get("triggered",0))
        evidence_ok=bool(g and g.get("sample_ok"))
        # Evidence gate: raw score can never create WATCH/ELITE by itself.
        if not evidence_ok:
            tier="INSUFFICIENT_EVIDENCE"
        else:
            q=float(r.get("evidence_score10") or 0)
            # Conservative first integration thresholds. Evidence quality is based on
            # Wilson lower confidence bounds, not naive hit rate.
            tier="ELITE" if q>=6.0 and triggered>=30 else ("WATCH" if q>=4.0 and triggered>=25 else "RESEARCH")
        r["tier"]=tier
        r["evidence_ok"]=evidence_ok
        r["triggered_sample"]=triggered
        r["explanation"]=self.explain(r,symbol,setup,direction)
        return r

    @staticmethod
    def explain(r,symbol,setup,direction):
        g=r.get("evidence_group")
        if not g:
            return f"{symbol} {setup} {direction}: insufficient comparable historical evidence."
        return (f"{symbol} {setup} {direction}: {g.get('triggered',0)} triggered comparables; "
                f"3R hit {g.get('hit_3r_pct',0):.1f}%, 5R hit {g.get('hit_5r_pct',0):.1f}%; "
                f"conservative evidence quality {r.get('evidence_score10')}/10.")
