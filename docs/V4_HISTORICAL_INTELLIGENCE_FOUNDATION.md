# V4 Historical Intelligence + Professor + Backtest Analytics Foundation

Research-only foundation. It does not change scoring, evidence, live policy, or deployment.

## Components
- `v4_historical_catalog.py`: read-only catalog for monthly Databento Parquet and legacy history.
- `v4_historical_intelligence.py`: deterministic chart/date-history/fingerprint/similar-day facts with `as_of` anti-lookahead.
- `v4_professor_historical.py`: deterministic natural-language routing for historical questions. Unknown requests return unsupported rather than fabricated statistics.
- `v4_backtest_intelligence.py`: dashboard-ready evidence summaries, Wilson confidence, EV and research artifact inventory.

## Design boundary
Historical data -> deterministic analytics -> Professor interpretation.
The Professor is not the calculator of market statistics.

## Examples
`Pull up NQ chart from March 1 2024 15m`
`How has GC moved on August 23 over the past 3 years?`
`Show me NQ days similar to March 1 2024`

## Safety
Blind/final-holdout files are read-only inputs. This package contains no fitting, threshold optimization, scoring mutation, database write, Git, push, or deploy operation.
