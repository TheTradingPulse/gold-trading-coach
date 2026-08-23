from __future__ import annotations
import math
from typing import Any, Dict
from v4_risk_target_policy import DEFAULT_POLICY, ResearchTargetPolicy, planned_levels

def _f(v):
    try:
        x = float(v)
        return None if math.isnan(x) else x
    except Exception:
        return None

def evaluate_outcome(candidate: Dict[str, Any], future, max_bars: int = 240,
                     policy: ResearchTargetPolicy = DEFAULT_POLICY) -> Dict[str, Any]:
    side = str(candidate.get("direction", "")).upper()
    entry = _f(candidate.get("entry"))
    stop = _f(candidate.get("stop"))

    if side not in ("LONG", "SHORT") or entry is None or stop is None:
        return {"outcome": "UNRESOLVED_PLAN", "entered": False}

    try:
        plan = planned_levels(candidate, policy)
    except ValueError:
        return {"outcome": "INVALID_RISK", "entered": False}

    risk = plan["risk_points"]
    primary = plan["primary_target"]
    stretch = plan["stretch_target"]

    entered = False
    entry_i = None
    raw_mfe_points = 0.0
    raw_mae_points = 0.0
    alive_mfe_points = 0.0
    alive_mae_points = 0.0
    primary_hit = False
    stretch_hit = False
    bars_to_primary = None
    bars_to_stretch = None
    stop_hit = False
    ambiguous = False
    outcome = "NOT_TRIGGERED"
    realized_r = None
    i = 0

    for i, (_, row) in enumerate(future.iloc[:max_bars].iterrows()):
        lo = float(row["low"])
        hi = float(row["high"])

        if not entered:
            if lo <= entry <= hi:
                entered = True
                entry_i = i
            else:
                continue

        if side == "LONG":
            favorable = max(0.0, hi - entry)
            adverse = max(0.0, entry - lo)
            candle_stop = lo <= stop
            candle_primary = hi >= primary
            candle_stretch = hi >= stretch
        else:
            favorable = max(0.0, entry - lo)
            adverse = max(0.0, hi - entry)
            candle_stop = hi >= stop
            candle_primary = lo <= primary
            candle_stretch = lo <= stretch

        # Raw excursion describes everything the candle printed after entry.
        raw_mfe_points = max(raw_mfe_points, favorable)
        raw_mae_points = max(raw_mae_points, adverse)

        # Trade-alive excursion is bounded by the actual stop. This prevents
        # -10R/-20R post-stop movement from contaminating trade statistics.
        alive_mfe_points = max(alive_mfe_points, favorable)
        alive_mae_points = max(alive_mae_points, min(adverse, risk))

        # Preserve existing V4 replay convention: target evidence on an OHLC
        # bar is registered before stop evidence, while ambiguity is flagged.
        if candle_primary and not primary_hit:
            primary_hit = True
            bars_to_primary = i - entry_i
        if candle_stretch and not stretch_hit:
            stretch_hit = True
            bars_to_stretch = i - entry_i

        if candle_stop:
            stop_hit = True
            if candle_primary or candle_stretch:
                ambiguous = True
            if stretch_hit:
                outcome = "T2_THEN_STOP"
            elif primary_hit:
                outcome = "T1_THEN_STOP"
            else:
                outcome = "STOP"
            realized_r = policy.stop_r
            break

        if stretch_hit:
            outcome = "T2_HIT"
            realized_r = policy.stretch_r
            break

    else:
        if entered:
            if stretch_hit:
                outcome = "T2_HIT"
                realized_r = policy.stretch_r
            elif primary_hit:
                outcome = "T1_HIT_OPEN"
            else:
                outcome = "EXPIRED"

    if not entered:
        return {
            "outcome": "NOT_TRIGGERED",
            "entered": False,
            "bars_observed": min(len(future), max_bars),
            "primary_r": policy.primary_r,
            "stretch_r": policy.stretch_r,
        }

    raw_mfe_r = raw_mfe_points / risk
    raw_mae_r = -raw_mae_points / risk
    alive_mfe_r = alive_mfe_points / risk
    alive_mae_r = -alive_mae_points / risk

    legacy_target_r = {
        name.upper(): abs(float(candidate[name]) - entry) / risk
        for name in ("t1", "t2", "t3")
        if candidate.get(name) is not None
    }

    # Preserve the legacy achieved_r contract for existing V4 callers/tests.
    # The new canonical research achievement is stored separately.
    legacy_hits = []
    if side == "LONG":
        for name in ("t1", "t2", "t3"):
            price = _f(candidate.get(name))
            if price is not None and raw_mfe_points >= max(0.0, price-entry):
                legacy_hits.append(name.upper())
    else:
        for name in ("t1", "t2", "t3"):
            price = _f(candidate.get(name))
            if price is not None and raw_mfe_points >= max(0.0, entry-price):
                legacy_hits.append(name.upper())

    research_achieved_r = policy.stretch_r if stretch_hit else policy.primary_r if primary_hit else 0.0

    # Backward compatibility:
    # - If the candidate supplies legacy t1/t2/t3 geometry, achieved_r reports
    #   the furthest supplied target actually reached.
    # - If no legacy targets are supplied, achieved_r falls back to the new
    #   canonical 3R/5R research achievement.
    achieved_r = (
        max((legacy_target_r[n] for n in legacy_hits), default=0.0)
        if legacy_target_r
        else research_achieved_r
    )

    return {
        "outcome": outcome,
        "entered": True,
        "bars_to_entry": entry_i,
        "bars_to_outcome": i - entry_i,
        "risk_points": risk,
        "primary_r": policy.primary_r,
        "stretch_r": policy.stretch_r,
        "primary_target": primary,
        "stretch_target": stretch,
        # Backward-compatible legacy target API: preserve the R geometry of
        # candidate-supplied t1/t2/t3 exactly as older V4 callers expect.
        "target_r": {
            name.upper(): abs(float(candidate[name]) - entry) / risk
            for name in ("t1", "t2", "t3")
            if candidate.get(name) is not None
        },
        # New research policy remains separate from legacy target geometry.
        "research_target_r": {"PRIMARY_3R": policy.primary_r, "STRETCH_5R": policy.stretch_r},
        "primary_hit": primary_hit,
        "stretch_hit": stretch_hit,
        "bars_to_primary": bars_to_primary,
        "bars_to_stretch": bars_to_stretch,
        "bars_to_target": {
            **({"T1": bars_to_primary} if bars_to_primary is not None else {}),
            **({"T2": bars_to_stretch} if bars_to_stretch is not None else {}),
        },
        "stop_hit": stop_hit,
        "raw_mfe_points": raw_mfe_points,
        "raw_mae_points": -raw_mae_points,
        "raw_mfe_r": raw_mfe_r,
        "raw_mae_r": raw_mae_r,
        "alive_mfe_points": alive_mfe_points,
        "alive_mae_points": -alive_mae_points,
        "alive_mfe_r": alive_mfe_r,
        "alive_mae_r": alive_mae_r,
        # Backward-compatible aliases now mean trade-alive excursion.
        "mfe_points": alive_mfe_points,
        "mae_points": -alive_mae_points,
        "mfe_r": alive_mfe_r,
        "mae_r": alive_mae_r,
        "achieved_r": achieved_r,
        "research_achieved_r": research_achieved_r,
        "realized_r": realized_r,
        "same_bar_ambiguous": ambiguous,
    }
