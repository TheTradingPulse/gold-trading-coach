# V4 Temporal Stability / Regime Sniper

Research-only layer designed to reduce validation-to-holdout decay.

It uses the existing contextual Evidence V4 database and preserves the 50/20/15/15 chronological discipline:
Discovery -> Calibration -> Validation -> Final untouched holdout.

Changes:
- temporal monthly survival gates
- market/setup/direction identity
- session, projected-R/R, 1H/4H trend, and volatility regime interactions
- Wilson confidence bounds
- calibration-before-freeze
- redundant rule pruning
- separate Elite and Grand Slam rules
- context-dependent 3R versus 5R target recommendation
- final holdout promotion gates

It does not modify V3.4 live behavior, existing V4 scoring, dashboard, deployment, Git branches, or production policy.
