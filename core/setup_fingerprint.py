"""The Trading Pulse - Setup Fingerprint Engine V2.8B.

Creates deterministic, JSON-safe descriptions of what the engine saw at a
specific market timestamp. It records observations; it does not claim that any
feature is predictive.
"""
from __future__ import annotations
from dataclasses import asdict, is_dataclass
from typing import Any, Optional
import hashlib
import json
import math

def _safe(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return None if not math.isfinite(value) else round(value, 8)
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if is_dataclass(value):
        return _safe(asdict(value))
    if hasattr(value, "item"):
        try:
            return _safe(value.item())
        except Exception:
            pass
    return str(value)

def _get(obj, name, default=None):
    return getattr(obj, name, default) if obj is not None else default

def _zone(z):
    if z is None:
        return None
    return _safe({
        "type": _get(z, "type"),
        "timeframe": _get(z, "timeframe"),
        "lower_bound": _get(z, "lower_bound"),
        "upper_bound": _get(z, "upper_bound"),
        "width_points": _get(z, "width_points"),
        "strength": _get(z, "strength"),
        "grade": _get(z, "grade"),
        "distance_points": _get(z, "distance_points"),
        "distance_pct": _get(z, "distance_pct"),
        "freshness_score": _get(z, "freshness_score"),
        "retest_count": _get(z, "retest_count"),
        "created_at": _get(z, "created_at"),
    })

def build_setup_fingerprint(state, clock=None) -> dict:
    c = _get(state, "confirmation")
    trade = _get(state, "trade")
    targets = _get(trade, "targets", []) or []
    target = targets[0] if targets else None

    raw = {
        "schema_version": "2.8B",
        "root_symbol": _get(state, "root_symbol"),
        "instrument_name": _get(state, "instrument_name"),
        "asset_class": _get(state, "asset_class"),
        "exchange": _get(state, "exchange"),
        "currency": _get(state, "currency"),
        "contract_selection": _get(state, "contract_selection"),
        "contract_symbol": _get(state, "contract_symbol"),
        "data_symbol": _get(state, "data_symbol"),
        "market_timestamp": _get(state, "market_timestamp"),
        "clock": clock.to_dict() if clock is not None else None,
        "market": {
            "current_price": _get(state, "current_price"),
            "market_bias": _get(state, "market_bias"),
            "alignment_score": _get(state, "alignment_score"),
            "trends": _get(state, "trends", {}),
            "market_session": _get(state, "market_session"),
            "news_risk": _get(state, "news_risk"),
        },
        "structure": {
            "higher_timeframe_context": _zone(_get(state, "higher_timeframe_context")),
            "execution_zone": _zone(_get(state, "selected_zone")),
            "opposing_zone_conflict": _get(state, "opposing_zone_conflict", False),
            "opposing_zone": _zone(_get(state, "opposing_zone")),
            "supply_zone_count": len(_get(state, "supply_zones", []) or []),
            "demand_zone_count": len(_get(state, "demand_zones", []) or []),
        },
        "confirmation": {
            "setup_state": _get(state, "setup_state"),
            "setup_direction": _get(state, "setup_direction"),
            "price_in_zone": _get(c, "price_in_zone"),
            "lower_timeframe_confirmed": _get(c, "lower_timeframe_confirmed"),
            "structural_trigger": _get(c, "structural_trigger"),
            "risk_validated": _get(c, "risk_validated"),
            "confirmation_timeframe": _get(c, "confirmation_timeframe"),
            "zone_interaction": _get(c, "zone_interaction"),
            "trigger_type": _get(c, "trigger_type"),
            "trigger_price": _get(c, "trigger_price"),
            "conditions_met": _get(c, "conditions_met"),
            "conditions_total": _get(c, "conditions_total"),
            "missing_conditions": _get(c, "missing_conditions", []),
        },
        "trade": {
            "direction": _get(trade, "direction"),
            "entry": _get(trade, "entry"),
            "stop": _get(trade, "stop"),
            "risk_points": _get(trade, "risk_points"),
            "risk_ticks": _get(trade, "risk_ticks"),
            "risk_dollars_per_contract": _get(trade, "risk_dollars_per_contract"),
            "target_price": _get(target, "price"),
            "reward_points": _get(target, "reward_points"),
            "reward_ticks": _get(target, "reward_ticks"),
            "reward_dollars_per_contract": _get(target, "reward_dollars_per_contract"),
            "rr_ratio": _get(target, "rr_ratio"),
        },
        "engine_versions": _get(state, "engine_versions", {}),
    }
    clean = _safe(raw)
    identity = json.dumps(clean, sort_keys=True, separators=(",", ":"))
    clean["fingerprint_id"] = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return clean
