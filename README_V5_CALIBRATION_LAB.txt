TRADING PULSE V5 CHRONOLOGICAL CALIBRATION LAB

Purpose
  Find out which V5 candidate features improve verified 3R-first outcomes.
  This is an audit and calibration tool, not a promise of profitability.

Safety
  - Reads databento_v5_evidence.db without modifying it.
  - Does not change dashboard.py.
  - Does not change V4, the V5 warehouse, or the V5 replay database.
  - Writes new output only under research_data\v5\calibration.

Chronology
  - Development: 2021-2023
  - Calibration: 2024
  - Untouched holdout: 2025
  The 2025 outcomes are not used to choose thresholds.

Run
  From C:\TradingPulse execute:
    .\RUN_V5_CALIBRATION_LAB.ps1

Upload the result ZIP printed at the end so the findings can be reviewed before
any grading, Elite qualification, or dashboard logic is changed.
