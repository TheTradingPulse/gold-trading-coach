# Phase 3I — Frozen 2026 GC Confirmation

This test freezes the only Phase 3H configuration that remained positive in the report-only 2025 period: original GC entry, point-in-time 1.0× five-minute ATR14 stop, and 5R target. It performs no parameter search.

If January–August 23, 2026 19:00 UTC GC one-minute data is missing, the first run obtains a Databento quote and stops without purchasing. The endpoint stays before the availability boundary Databento disclosed for this account. Review the cost and explicitly rerun with `-ApproveDownload` to authorize the historical request.

Databento symbology uses `GC.v.0` as continuous input and `instrument_id` as
the supported output representation. Output symbol labels do not affect the
timestamp/OHLCV replay or the frozen hypothesis.
