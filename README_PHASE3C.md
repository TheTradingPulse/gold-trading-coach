# Trading Pulse Canonical Phase 3C

This package adds a shared, fail-closed opportunity lifecycle between the exact-parity V6 detector and any future dashboard adapter.

It does **not** change the dashboard, overwrite a database, or promote V6 live. It classifies recent triggered zones using closed 5-minute bars and exposes only unresolved `TRIGGERED_RECENT`, `ACTIVE_RISK`, and `MANAGING` records in its shadow output. Stops, completed targets, expired records, and same-bar ambiguity are excluded.

The 576-bar expiration and 5R final target are explicit provisional operating parameters. They must be calibrated; they are not presented as proven edge.

Install by extracting into `C:\TradingPulse`, then run:

```powershell
.\RUN_CANONICAL_PHASE3C_LIFECYCLE.ps1
```
