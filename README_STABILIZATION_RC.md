# Trading Pulse Stabilization Release Candidate

This package prepares the current Trading Pulse system for a controlled GitHub
and Railway release. It does not alter research databases or Phase 3L output.

Changes:

- Hardens `.gitignore` against credentials, databases, purchased market data,
  archives, backups, runtime outputs, and local environments.
- Adds a fail-closed pre-publish gate that scans the exact Git candidate set.
- Establishes `core/live_grading_service.py` as the production grading authority.
- Prevents a historical rule match from issuing a live Elite star before
  canonical first-touch execution verification.
- Reduces unnecessary work against the delayed Yahoo development feed by using
  a configurable 120-second refresh and longer safe cache windows.
- Caches repeated evidence, experiment, and Professor analytics queries.
- Adds focused regression tests and a recoverable rollback directory.

No Git commit, push, deployment, data purchase, or research promotion is
performed automatically.

