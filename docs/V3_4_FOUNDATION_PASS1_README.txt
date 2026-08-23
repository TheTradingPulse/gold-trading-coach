TRADING PULSE V3.4 FOUNDATION - PASS 1

PURPOSE
Repository hygiene and a recoverable clean baseline before performance or trading-logic changes.

THIS PASS DOES:
- Archives legacy/local root artifacts OUTSIDE C:\TradingPulse (never deletes them).
- Adds tests/, scripts/, and docs/ scaffolding.
- Expands .gitignore for known local development artifacts and research cache.
- Adds core/version.py as the canonical version location for NEW code.
- Removes stale V2.5.1 wording from startup.sh only; startup behavior is unchanged.
- Compiles all runtime Python and verifies critical architecture markers.
- Verifies dashboard.py SHA256 is unchanged by this pass.

THIS PASS DOES NOT:
- Change dashboard.py.
- Change MarketState, setup scoring, journal behavior, backtesting, Professor behavior, or data providers.
- Delete research_data.
- Commit, push, deploy, or touch Railway/production.

IMPORTANT
Legacy evidence version strings (for example 3.3C in journal_tracker.py) are intentionally NOT rewritten.
Changing those blindly would corrupt provenance. They will be migrated deliberately in the evidence pass.
