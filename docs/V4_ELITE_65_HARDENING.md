# V4 Elite 65% Hardening

This is a research-only precision hardening pass.

A 65% win rate is **not** assumed to be necessary for profitability. At fixed 3R, the theoretical break-even hit rate before costs is 25%; at fixed 5R it is 16.7%. Requiring 65% therefore targets exceptional precision and may sharply reduce trade frequency.

This build does not manufacture a 65% class. It searches a precision/sample-size frontier, freezes the selected rules before the final holdout, and only reports a 65% candidate if the untouched holdout itself reaches >=65% at 3R with Wilson lower bound >=60%, >=200 triggered examples, cross-slice robustness, and slippage stress survival.

Adversarial tests include market, direction, session, leave-one-market-out, rolling month, losing streak, 3R/5R, and 0.05R-0.30R execution-cost stress.

No live scoring, dashboard, deployment, commit, or push is performed.
