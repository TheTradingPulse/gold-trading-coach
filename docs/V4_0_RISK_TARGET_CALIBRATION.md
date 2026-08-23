# Trading Pulse V4 — 3R / 5R Research Calibration

This research layer starts with a simple falsifiable policy:

- stop = -1R
- primary objective = +3R
- stretch objective = +5R
- raw excursion remains uncapped for research
- trade-alive adverse excursion is capped at the actual -1R stop
- a 17R raw move remains visible as MFE research, but is not described as a planned 17:1 trade

The 3R / 5R policy is a research baseline, not a permanent truth. V4 stores enough evidence to compare:
trigger rate, 3R hit rate, 5R hit rate, probability of 5R after 3R, stop rate, score buckets,
setup type, direction, raw excursion, and trade-alive excursion.

IMPORTANT:
This package does not modify dashboard.py, TradingView rendering, the live V3.4 Elite threshold,
the live journal, opportunity_policy.py, or the canonical setup scoring engine.
The goal is to collect trustworthy evidence before changing live policy.
