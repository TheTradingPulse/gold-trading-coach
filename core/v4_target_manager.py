def target_plan(decision):
    """Research target plan. 3R remains primary unless 5R has a meaningful EV advantage."""
    e3=float(decision.get("ev_3r",0));e5=float(decision.get("ev_5r",0))
    if e5>e3+.10:
        return {"primary":"3R","runner":"5R","mode":"3R_PLUS_5R_RUNNER",
                "reason":"5R posterior EV exceeds 3R by a meaningful margin"}
    return {"primary":"3R","runner":None,"mode":"FIXED_3R",
            "reason":"5R edge is not sufficiently larger than 3R"}
