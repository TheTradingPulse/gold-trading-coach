# Stage 1 — Integration contract

Stage 1 makes every result comparable before any further strategy search.

## Required output

Every detector must emit `CanonicalTradeRecord`. Charts, replay, grading,
journaling and Professor explanations consume the same immutable values.

## Metric definitions

- A candidate exists only after its required confirmation candle closes.
- Entry, stop, T1, T2 and 3R are frozen at confirmation.
- Risk is reported in points, ticks and executable dollars.
- `$300` is the maximum permitted setup risk, never the default risk.
- `1R`, `2R` and `3R` use the same entry and structural stop.
- Same-resolution stop/target collisions are ambiguous unless finer data resolves order.
- Development, calibration, holdout and live-shadow rows never mix.
- Win rate is always reported with target R, sample, costs and split.

## Purge method

Nothing is deleted during discovery. Modules are classified as production,
research-only or quarantine candidates in `config/runtime_authority.json`.
Quarantine candidates are disconnected only after import tracing and tests prove
that production no longer depends on them. Raw data and audit evidence are preserved.

## Stage 1 exit gate

- One contract passes validation across chart, replay and journal adapters.
- All reported targets recompute exactly from entry and risk.
- No record above the risk ceiling can become trade-ready.
- Runtime modules are explicitly allow-listed.
- GitHub quality checks pass from a clean checkout.
