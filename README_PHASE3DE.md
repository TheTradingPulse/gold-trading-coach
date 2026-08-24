# Canonical Phase 3D/E

This shadow-only lab combines native 1R-through-20R first-touch classification with chronological filter discovery.

Each R target is reclassified independently so same-candle stop/target ambiguity is identified at that target. Filters are discovered on the earliest 60% of timestamps, checked on the next 20%, and reported on the final untouched 20%. No candidate is promoted live.

Run after extracting into `C:\TradingPulse`:

```powershell
.\RUN_CANONICAL_PHASE3DE_RR_FILTER_LAB.ps1
```
