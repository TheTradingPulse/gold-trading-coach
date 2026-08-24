# Trading Pulse Data Truth RC

This release candidate prevents research outputs from being presented as live-authorized facts.

- Current candles are labeled as delayed Yahoo reference data and not execution eligible.
- Evidence confidence is blank unless the newest integrity-checked report explicitly has `live_promotion: true`.
- The visual score is labeled **Structure Score (not win probability)**.
- The legacy V3/Yahoo manual replay is blocked while its controls remain in place.
- V5/V7 reports remain read-only and are shown as research only.
- Research databases and the running Phase 3L job are not modified.

Install from `C:\TradingPulse` with `INSTALL_DATA_TRUTH_RC.ps1`, then refresh the dashboard.
