"""
The Trading Pulse V2.10E - Data Integrity / Feed Provenance

Purpose:
- Tell the truth about the active market-data source.
- Never label Yahoo Finance futures as real-time.
- Carry source / symbol / contract mode into MarketState professor context.
- Block broker/executable readiness when the active feed is delayed or stale.

This module does NOT alter prices or attempt to make Yahoo match Tradovate.
"""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

SOURCE_ID = "yahoo_finance"
SOURCE_NAME = "Yahoo Finance"
REQUESTED_SYMBOL = "GC=F"
CONTRACT_MODE = "CONTINUOUS_FRONT_MONTH"
DISPLAY_CONTRACT = "GC=F / Front Month"
EXPECTED_DELAY_MINUTES = 15

@dataclass(frozen=True)
class FeedStatus:
    source_id: str
    source_name: str
    requested_symbol: str
    contract_mode: str
    display_contract: str
    status: str
    age_minutes: Optional[float]
    expected_delay_minutes: int
    realtime: bool
    execution_eligible: bool
    reason: str
    market_timestamp: Optional[str]

    def to_dict(self):
        return asdict(self)


def _utc(value):
    if value is None:
        return None
    try:
        import pandas as pd
        ts = pd.Timestamp(value)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return ts
    except Exception:
        return None


def evaluate_feed_status(market_timestamp, now=None, source_id=SOURCE_ID):
    """Return canonical feed truth for the candle powering MarketState.

    Yahoo is intentionally DELAYED even when its newest candle is recent.
    STALE means the stored candle is older than the expected delayed-feed window.
    OFFLINE means no usable timestamp exists.
    Tradovate is reserved for the future adapter and is not activated here.
    """
    ts = _utc(market_timestamp)
    if ts is None:
        return FeedStatus(
            SOURCE_ID, SOURCE_NAME, REQUESTED_SYMBOL, CONTRACT_MODE,
            DISPLAY_CONTRACT, "OFFLINE", None, EXPECTED_DELAY_MINUTES,
            False, False, "No usable market timestamp is stored.", None,
        )

    now_ts = _utc(now) if now is not None else _utc(datetime.now(timezone.utc))
    age = max(0.0, (now_ts - ts).total_seconds() / 60.0)

    if source_id == "tradovate":
        # Future adapter contract. Not used by V2.10E Yahoo ingestion.
        if age <= 2.0:
            return FeedStatus(
                "tradovate", "Tradovate", "GC", "SPECIFIC_CONTRACT",
                "Tradovate futures contract", "REALTIME", round(age, 2), 0,
                True, True, "Real-time Tradovate feed is current.", ts.isoformat(),
            )
        return FeedStatus(
            "tradovate", "Tradovate", "GC", "SPECIFIC_CONTRACT",
            "Tradovate futures contract", "STALE", round(age, 2), 0,
            True, False, "Tradovate feed timestamp is stale.", ts.isoformat(),
        )

    # Yahoo GC=F is a delayed continuous/front-month development feed.
    # Give normal quote delay + ingestion cadence some room before calling it stale.
    stale_after = EXPECTED_DELAY_MINUTES + 20
    if age <= stale_after:
        status = "DELAYED"
        reason = (
            "Yahoo GC=F is delayed/continuous futures data. Useful for research, "
            "education and higher-timeframe development; not broker-execution eligible."
        )
    else:
        status = "STALE"
        reason = f"Newest stored Yahoo candle is {age:.1f} minutes old."

    return FeedStatus(
        SOURCE_ID, SOURCE_NAME, REQUESTED_SYMBOL, CONTRACT_MODE,
        DISPLAY_CONTRACT, status, round(age, 2), EXPECTED_DELAY_MINUTES,
        False, False, reason, ts.isoformat(),
    )


def provenance_dict(market_timestamp, now=None):
    return evaluate_feed_status(market_timestamp, now=now).to_dict()
