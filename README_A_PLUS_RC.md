# Trading Pulse V4 A+ Release Candidate

Focused whole-system hardening pass based on the 2026-08-23 source snapshot.

Changes:
- Corrects misleading dashboard terminology: legacy raw-score/structural Elite is explicitly distinguished from V4 evidence-qualified Elite/Grand Slam.
- Removes the remaining amber/gold informational accent from the dashboard.
- Corrects Backtest Lab copy so V3 backtests are not represented as the same grading policy as V4 evidence-qualified research.
- Adds a fail-closed release health check for all three frozen rule sets, the 480-file raw audit, the 480 canonical manifest, Grand Slam raw-score guard, and delayed-feed execution guard.
- No scoring thresholds or frozen rules are changed.
- No databases or historical data are modified.

Important: the current live_data_engine is Yahoo Finance GC=F delayed development data, not a real-time CME feed. The dashboard can be used for observation, but it is not true tick/live shadow until a real-time provider adapter is installed.
