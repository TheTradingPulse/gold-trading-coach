"""Streamlit renderer for the V4 evidence-qualified Backtest Lab."""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from v4_live_integration import evidence_lab_snapshot


def _number(value: Any, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "--"
    try:
        return f"{float(value):,.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return "--"


def _number_value(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def render_v4_backtest_lab(symbols: list[str]) -> None:
    st.markdown("## V4 EVIDENCE LAB")
    st.caption(
        "Five-year point-in-time evidence, conservative confidence bounds, "
        "out-of-sample validation, and walk-forward stability. Raw structure "
        "scores cannot manufacture an Elite classification."
    )

    initial = evidence_lab_snapshot()
    system = initial["status"]
    health = system["release_health"]
    if system["ready"]:
        st.success(
            f"V4 RELEASE DATA READY - {health['passed']}/{health['total']} release checks passed."
        )
    else:
        st.error(
            f"V4 RELEASE BLOCKED - {health['passed']}/{health['total']} release checks passed. "
            "No live Elite or Watch tier will be issued until the complete evidence bundle is installed."
        )

    checks = pd.DataFrame(
        [
            {
                "Check": row.get("name"),
                "Status": "PASS" if row.get("ok") else "BLOCKED",
                "Detail": row.get("detail"),
            }
            for row in health.get("checks", [])
        ]
    )
    with st.expander("RELEASE DATA HEALTH", expanded=not system["ready"]):
        if len(checks):
            st.dataframe(checks, hide_index=True, width="stretch")
        else:
            st.caption("No release-health checks were available.")

    base_metrics = initial.get("metrics") or {}
    base_breakdowns = base_metrics.get("breakdowns") or {}
    setup_values = [str(x.get("value")) for x in base_breakdowns.get("setup_type", []) if x.get("value")]
    compact = bool(base_metrics.get("compact"))
    filters: dict[str, Any] = {}
    if compact:
        st.info(
            "Production compact mode: showing the complete precomputed evidence summary "
            "and one-dimensional breakdowns without shipping the 1.57 GB research databases."
        )
        lab = initial
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            selected_symbol = st.selectbox("MARKET", ["ALL", *symbols], key="v4_lab_symbol")
        with c2:
            selected_direction = st.selectbox("DIRECTION", ["ALL", "LONG", "SHORT"], key="v4_lab_direction")
        with c3:
            selected_setup = st.selectbox(
                "SETUP TYPE",
                ["ALL", *sorted(set(setup_values))],
                key="v4_lab_setup",
            )
        if selected_symbol != "ALL":
            filters["symbol"] = selected_symbol
        if selected_direction != "ALL":
            filters["direction"] = selected_direction
        if selected_setup != "ALL":
            filters["setup_type"] = selected_setup
        lab = evidence_lab_snapshot(filters)
    metrics = lab.get("metrics") or {}
    if not metrics.get("available"):
        st.warning(
            "The V4 contextual evidence database is not installed in this checkout. "
            "Install research_data/v4/context_evidence_v4.db to test historical evidence."
        )
        return

    summary = metrics.get("summary") or {}
    reports = lab.get("reports") or {}
    temporal = reports.get("temporal_regime_sniper/temporal_regime_report.json") or {}
    promoted_holdout = ((temporal.get("final_holdout") or {}).get("elite") or {})
    promotion = temporal.get("promotion") or {}

    st.markdown("#### PROMOTED ELITE - FINAL HOLDOUT")
    cards = st.columns(6)
    values = (
        ("ASSIGNED", f"{int(promoted_holdout.get('assigned') or 0):,}"),
        ("TRIGGERED", f"{int(promoted_holdout.get('triggered') or 0):,}"),
        ("3R HIT RATE", _number((_number_value(promoted_holdout.get("p3")) or 0) * 100, 1, "%")),
        ("5R HIT RATE", _number((_number_value(promoted_holdout.get("p5")) or 0) * 100, 1, "%")),
        ("3R WILSON LOW", _number((_number_value(promoted_holdout.get("w3")) or 0) * 100, 1, "%")),
        ("3R EXPECTANCY", _number(promoted_holdout.get("ev3"), 2, "R")),
    )
    for column, (label, value) in zip(cards, values):
        column.metric(label, value)

    if promotion.get("elite") is True:
        st.success("Temporal-regime Elite passed the frozen final-holdout promotion gate.")
    if promotion.get("grand_slam") is False:
        st.warning("Grand Slam did not pass its promotion gate and remains disabled in live classification.")
    st.caption("Wilson Low is the conservative 95% lower confidence bound used by promotion gates.")

    st.markdown("#### COMPLETE EVIDENCE WAREHOUSE")
    warehouse_cards = st.columns(6)
    warehouse_values = (
        ("OBSERVATIONS", f"{int(summary.get('observations') or 0):,}"),
        ("TRIGGERED", f"{int(summary.get('triggered') or 0):,}"),
        ("3R HITS", f"{int(summary.get('hit_3r') or 0):,}"),
        ("5R HITS", f"{int(summary.get('hit_5r') or 0):,}"),
        ("OVERALL 3R", _number(summary.get("hit_3r_pct"), 1, "%")),
        ("AVG REALIZED", _number(summary.get("avg_realized_r"), 2, "R")),
    )
    for column, (label, value) in zip(warehouse_cards, warehouse_values):
        column.metric(label, value)

    breakdowns = metrics.get("breakdowns") or {}
    left, right = st.columns(2)
    with left:
        st.markdown("#### MARKET EVIDENCE")
        market_rows = breakdowns.get("symbol", [])
        if market_rows:
            st.dataframe(pd.DataFrame(market_rows), hide_index=True, width="stretch")
        else:
            st.caption("No market evidence matches these filters.")
    with right:
        st.markdown("#### SETUP EVIDENCE")
        setup_rows = breakdowns.get("setup_type", [])
        if setup_rows:
            st.dataframe(pd.DataFrame(setup_rows), hide_index=True, width="stretch")
        else:
            st.caption("No setup evidence matches these filters.")

    st.markdown("#### VALIDATION ARTIFACTS")
    if not reports:
        st.warning("OOS and walk-forward validation reports are missing. Release remains blocked.")
    for name, report in reports.items():
        label = name.replace("v4_", "").replace(".json", "").replace("_", " ").upper()
        with st.expander(label):
            if name == "v4_oos_validation.json" and report.get("passes_ordering") is False:
                st.error("Rejected legacy calibration: tier ordering failed out of sample and is not used live.")
            if name.endswith("elite_65_hardening_report.json") and report.get("status") == "KEEP_RESEARCH_ONLY":
                st.warning("Research-only hardening artifact; it is not an active live policy.")
            st.json(report)

    st.info(
        "This page reads the frozen V4 evidence warehouse. It does not rerun the "
        "legacy V3 raw-score experiment or silently alter trading rules."
    )
