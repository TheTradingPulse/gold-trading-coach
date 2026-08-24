# V4 Elite Discovery + Nested Validation

Research-only system for discovering evidence-backed Elite and Grand Slam contextual rules.

## Chronological partitions
- 50% Discovery
- 20% Calibration
- 15% Validation
- 15% Final untouched holdout

Candidate contextual rules are discovered only in the first partition, must survive calibration,
are tested on validation, frozen, and only then evaluated on the final holdout.

The build deliberately does not lower the installed Elite/Grand Slam policy thresholds and does
not modify production scoring. Promotion requires final-holdout evidence.
