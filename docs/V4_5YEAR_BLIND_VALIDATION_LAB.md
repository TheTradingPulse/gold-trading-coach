# V4 Five-Year Blind Validation Lab

This package joins the three recent workstreams:

1. Elite/Grand-Slam evidence review and 65% hardening.
2. Databento GLBX.MDP3 2021-2025 1-minute historical library.
3. Historical Intelligence / Professor / Backtest analytics foundation.

## Non-negotiable research boundary
The 2021-2025 library is validation evidence. This package does not learn scoring thresholds from it, modify live policy, deploy, commit, or push. Frozen rules are to be evaluated unchanged first.

## Data
Expected raw library: 480 monthly Parquet files, 8 markets (GC SI ES NQ YM RTY CL NG), 2021-2025. Canonical build creates 15m, 1H, and 4H derivatives while leaving raw 1m untouched.

Databento warned that 2025-11-28 was degraded. It is registered as a quality flag, not silently deleted.

## Metrics
The lab supports 3R/5R hit rate, Wilson lower bound, average/expectancy R, profit factor, max loss streak, and slicing by market/year/month/session/setup/direction/tier/grade.

## Professor
HistoricalProfessorBridge returns factual packets only. Missing validation is explicitly INSUFFICIENT DATA. It can retrieve historical chart packets and validation summaries without inventing probabilities.

## Next integration
After canonical build passes, wire the existing contextual replay engine to the canonical_5y store and write its observations to a NEW five_year_blind_validation evidence file/store. Do not point it at production/live evidence. Then run FiveYearBlindValidationLab.analyze() over those observations.
