TRADING PULSE V5 POINT-IN-TIME REPLAY

Why this run is required
  The original V5 candidate timestamp used the start of the final 15-minute
  departure candle even though its completed OHLC was required to identify the
  setup. Higher-timeframe values were also left-labeled and could include an
  unfinished 1H, 4H, or daily candle.

Corrections
  - Candidate detection occurs when the third departure candle closes.
  - 1H, 4H, and daily values become available only at candle close.
  - Execution begins at the first one-minute candle at/after detection.
  - Uncertain same-minute order remains ambiguous rather than being guessed.

Safety
  This run writes a separate database under:
    research_data\v5\replay_point_in_time

  It does not modify the original replay, V5 warehouse, V4 evidence, raw data,
  dashboard, grading system, or live application.

