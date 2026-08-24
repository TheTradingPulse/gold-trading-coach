# Phase 3J — Controlled 2026 Data Acquisition

This package acquires only the next evidence layer needed by Trading Pulse:

- Remaining standard contracts: SI, ES, NQ, YM, RTY, CL, NG (`ohlcv-1m`)
- Actual micro contracts: MGC, SIL, MES, MNQ, MYM, M2K, MCL, MNG (`ohlcv-1m`)

Every missing symbol is quoted before any download. Existing destination files
are skipped. `-ApproveCore` is required for purchases, and the combined missing
cost must not exceed `-MaxCostUSD` (default $25). The downloader uses continuous
front-month input and supported instrument-ID output. It does not modify the
dashboard, canonical detectors, prior databases, or Phase 3I results.

Compatibility note: quote requests omit `stype_out` because the installed
Databento SDK does not accept that argument in `metadata.get_cost`; download
requests explicitly use `instrument_id` output.

Full-period one-second and BBO data are intentionally not purchased here. Those
high-volume schemas should be requested only around candidate entry windows
after the cross-market replay identifies them.
