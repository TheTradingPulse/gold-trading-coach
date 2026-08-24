# Phase 3K — Five-Year Micro Acquisition

Acquires one-minute continuous-contract OHLCV from 2021-01-01 through
2026-01-01 for MGC, SIL, MES, MNQ, MYM, M2K, MCL, and MNG.

Safety controls:

- Quotes every missing file before purchasing.
- Requires `-ApprovePurchase`.
- Refuses the entire run if the missing quote exceeds `-MaxCostUSD`.
- Defaults to a $45 hard cap.
- Requires at least 2 GB free disk space before the first purchase.
- Writes each symbol atomically and skips completed files on rerun.
- Does not modify the dashboard, canonical models, or existing databases.
