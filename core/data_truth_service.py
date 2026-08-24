"""Fail-closed provenance for every production-facing Trading Pulse statistic."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class TruthStatus:
    market_source: str
    market_execution_eligible: bool
    evidence_source: str | None
    evidence_generated_utc: str | None
    evidence_integrity: str | None
    live_promotion: bool
    warning: str
    holdout: dict[str, Any] | None = None


def _newest(pattern: str) -> Path | None:
    paths = [p for p in ROOT.glob(pattern) if p.is_file()]
    return max(paths, key=lambda p: p.stat().st_mtime) if paths else None


def _read(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def truth_status() -> TruthStatus:
    """Return only audited facts. Missing or non-promoted evidence stays unavailable."""
    phase3i_path = _newest("research_data/v7/phase3i_confirmation/*/phase3i_report.json")
    phase3i = _read(phase3i_path)
    v5_path = _newest("research_data/v5/calibration_point_in_time/**/v5_point_in_time_calibration_report.json")
    if v5_path is None:
        candidate = ROOT / "research_data/v5/calibration_point_in_time/v5_point_in_time_calibration_report.json"
        v5_path = candidate if candidate.exists() else None
    v5 = _read(v5_path)

    source_path = phase3i_path or v5_path
    source = None if source_path is None else str(source_path.relative_to(ROOT))
    report = phase3i or v5 or {}
    integrity = report.get("integrity")
    promoted = bool(report.get("live_promotion") is True and integrity == "ok")

    holdout = None
    if v5 and isinstance(v5.get("baseline"), dict):
        raw = v5["baseline"].get("holdout")
        if isinstance(raw, dict):
            holdout = dict(raw)

    if source is None:
        warning = "Canonical V5/V7 evidence report not found. Historical confidence and performance are unavailable."
    elif not promoted:
        warning = "Newest audited research is installed but is not approved for live promotion. It may be displayed as research, never as a trade grade or probability."
    else:
        warning = "Live evidence promotion is active."

    return TruthStatus(
        market_source="Yahoo delayed reference feed",
        market_execution_eligible=False,
        evidence_source=source,
        evidence_generated_utc=report.get("created_utc") or report.get("generated_utc"),
        evidence_integrity=integrity,
        live_promotion=promoted,
        warning=warning,
        holdout=holdout,
    )


def allow_manual_backtest() -> bool:
    """Legacy V3 replay must never masquerade as the canonical V5/V7 lab."""
    return False

