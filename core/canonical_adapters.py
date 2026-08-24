"""Adapters into canonical contracts; no policy promotion occurs here."""
from __future__ import annotations

from typing import Any, Mapping
from canonical_contracts import CanonicalOutcome, CanonicalSetup


def _f(value):
    try: return float(value) if value is not None else None
    except (TypeError, ValueError): return None


def from_live_candidate(candidate: Any, detector_version: str = "3.1E") -> CanonicalSetup:
    zone=str(getattr(candidate,"zone_type","UNKNOWN")).upper()
    direction="LONG" if zone=="DEMAND" else "SHORT" if zone=="SUPPLY" else "UNKNOWN"
    raw=_f(getattr(candidate,"setup_score",None)); score=raw/10 if raw is not None and raw>10 else raw
    return CanonicalSetup(
        setup_id=str(getattr(candidate,"candidate_id","")),source_generation="LIVE_V3",
        detector_version=detector_version,symbol=str(getattr(candidate,"symbol","GC")).upper(),
        direction=direction,pattern=zone,timeframe=str(getattr(candidate,"timeframe","")),
        formed_at=None,entry_ts=None,entry=_f(getattr(candidate,"projected_entry",None)),
        stop=_f(getattr(candidate,"projected_stop",None)),
        risk=(abs(_f(getattr(candidate,"projected_entry",None))-_f(getattr(candidate,"projected_stop",None)))
              if _f(getattr(candidate,"projected_entry",None)) is not None and _f(getattr(candidate,"projected_stop",None)) is not None else None),
        structure_score10=score,evidence_score10=None,execution_status="UNVERIFIED",
        attributes={"zone_quality":_f(getattr(candidate,"zone_quality_score",None)),
                    "freshness":_f(getattr(candidate,"freshness_score",None)),
                    "projected_rr":_f(getattr(candidate,"projected_rr",None)),
                    "lifecycle":str(getattr(candidate,"lifecycle",""))})


def from_v6_row(row: Mapping[str, Any]) -> tuple[CanonicalSetup, CanonicalOutcome]:
    direction=str(row.get("direction") or "UNKNOWN").upper(); score=_f(row.get("ota_score"))
    setup=CanonicalSetup(
        setup_id=str(row.get("zone_id") or ""),source_generation="V6_PROFESSIONAL_ZONE",
        detector_version="V6_PROFESSIONAL_ZONE_1",symbol=str(row.get("symbol") or "").upper(),
        direction=direction,pattern=str(row.get("pattern") or "UNKNOWN").upper(),timeframe="5m",
        formed_at=str(row.get("formed_at")) if row.get("formed_at") is not None else None,
        entry_ts=str(row.get("entry_ts")) if row.get("entry_ts") is not None else None,
        entry=_f(row.get("entry")),stop=_f(row.get("stop")),risk=_f(row.get("risk")),
        structure_score10=score,evidence_score10=None,execution_status="HISTORICALLY_REPLAYED",
        attributes={k:row.get(k) for k in ("base_candles","departure_ratio","strength_score","time_score",
                    "freshness_score","trend_score","curve_score","profit_score","profit_room_r","curve_position")})
    outcome=CanonicalOutcome(setup.setup_id,"V6_MAX_R_1",_f(row.get("max_verified_r")),
                             _f(row.get("max_possible_r")),False,0.0)
    return setup,outcome
