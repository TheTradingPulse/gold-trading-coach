# Trading Pulse system reset

## Source of truth

- Repository: `TheTradingPulse/gold-trading-coach`
- Production: `main` only
- Active work: `codex/system-reset-20260827`
- Changes reach `main` only through a pull request with a passing quality gate.
- ZIP installers are retired for repository-owned code.
- Local market data and large research warehouses stay outside Git.

## What the audit found

- The repository contains four long-lived branches and more than 100 overlapping engine/research modules.
- A clean checkout compiles, but the legacy named test is not self-contained.
- There was no continuous-integration workflow protecting `main`.
- The whole-system audit assumes a local Downloads path and crashes in a clean Linux checkout.
- The legacy 4H trend classifier is dominated by a lagging 50-period average and can contradict current swing structure.
- Zone touch, setup validity, outcome resolution, and chart selection have not always been kept separate.

## Frozen architecture rules

1. `MarketState` remains the single runtime source of truth.
2. Detection uses only information available before entry.
3. A zone touch is context, never an automatic order.
4. Trend continuations require 4H/1H directional agreement and a completed 15m trigger.
5. Countertrend entries require an explicit reversal structure break.
6. Structural risk may be less than $300; $300 is the hard maximum, never the default.
7. A trade needs at least 2R unobstructed room before the nearest opposing structure.
8. Charts show Entry, Stop, T1 and T2 only, beginning at the actionable entry timestamp.
9. Outcome-selected winners may be used for visual study, never to define a detector.
10. No strategy is promoted from point estimates without chronological holdout evidence.

## Next implementation order

1. Make the test/audit tools portable and green in CI.
2. Consolidate duplicate engines behind one canonical interface.
3. Build a versioned visual benchmark containing accepted and rejected examples.
4. Require the visual gate before replay/outcome evaluation.
5. Re-run GC calibration, then expand to other markets without hard-coded GC assumptions.
