"""Trading Pulse V3.0B/3.0C cross-market deterministic setup scanner."""
from __future__ import annotations
from instruments import get_enabled_symbols
from market_state_builder import build_market_state
from setup_candidate_engine import build_setup_candidates
from multi_market_validation import validate_candidate

ENGINE_VERSION = "3.0C"

def scan_markets(symbols=None, minimum_score=82.0, top_per_symbol=3):
    universe = list(symbols or get_enabled_symbols())
    rows=[]; errors={}; validation_failures=[]
    for symbol in universe:
        try:
            state=build_market_state(symbol)
            candidates=sorted(build_setup_candidates(state),key=lambda c:c.setup_score,reverse=True)
            accepted=0
            for c in candidates:
                if float(c.setup_score) < float(minimum_score):
                    continue
                validation=validate_candidate(c)
                if not validation.valid:
                    validation_failures.append({"symbol":symbol,"candidate_id":c.candidate_id,"errors":list(validation.errors)})
                    continue
                rows.append({
                    "symbol":symbol,
                    "score":round(float(c.setup_score)/10,1),
                    "timeframe":c.timeframe,
                    "side":"LONG" if c.zone_type=="demand" else "SHORT",
                    "zone_type":c.zone_type,
                    "lower":c.lower_bound,
                    "upper":c.upper_bound,
                    "lifecycle":c.lifecycle,
                    "candidate_id":c.candidate_id,
                    "preview_risk_points":validation.preview_risk_points,
                    "preview_risk_ticks":validation.preview_risk_ticks,
                    "preview_risk_dollars":validation.preview_risk_dollars,
                    "preview_rr":validation.preview_rr,
                    "contract_validated":True,
                    "execution_eligible":False,
                })
                accepted += 1
                if accepted >= int(top_per_symbol):
                    break
        except Exception as exc:
            errors[symbol]=str(exc)
    rows.sort(key=lambda x:(-x["score"],x["symbol"],x["timeframe"]))
    return {
        "setups":rows,
        "errors":errors,
        "validation_failures":validation_failures,
        "symbols_scanned":len(universe),
        "engine_version":ENGINE_VERSION,
    }
