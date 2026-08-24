# Trading Pulse V4 Live Evidence Integration

Release candidate integration pass dated 2026-08-23.

## Active behavior

- Promoted frozen temporal-regime evidence rules are authoritative on the Command Center.
- Raw setup scores are displayed only as Structure Score.
- Raw score and the legacy composite cannot create Elite or Watch.
- A missing or incomplete V4 evidence bundle fails closed as INSUFFICIENT EVIDENCE.
- Automatic paper journaling requires a V4 evidence-qualified Elite tier.
- Entry, stop, targets, invalidation, and lifecycle remain deterministic engine values.
- The Backtest tab reads the frozen V4 contextual evidence warehouse, OOS report,
  walk-forward report, and release-health checks.
- The legacy V3.4E Backtest UI is retained only as inert audit source.

## Required V4 release data

Install the derived evidence bundle under `research_data/v4/`, including:

- `v4_calibration.json` (retained for research/audit; rejected legacy tier ordering is not live)
- `context_evidence_v4.db`
- frozen 65, nested, and temporal rules
- canonical five-year manifest and raw 480-file audit
- `v4_oos_validation.json`
- `v4_walkforward_report.json`

The promoted temporal Elite passed final holdout. Grand Slam did not pass its
promotion gate and remains disabled. The earlier calibrated tier model failed
out-of-sample ordering and is shown only as a rejected audit artifact.

The application intentionally blocks evidence-qualified tiers when any mandatory
release-health artifact is unavailable.

## Security correction

Production Railway credentials were removed from all maintenance scripts. These
scripts now require `DATABASE_URL` from the environment. Destructive reset scripts
also require the explicit `ALLOW_DATA_RESET=YES` guard.
