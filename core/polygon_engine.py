"""
Polygon.io Data Engine for Gold Trading Coach
Handles real-time and historical Gold price data
"""
import pandas as pd
import os
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime, timedelta

# Load API key
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)
POLYGON_KEY = os.getenv("POLYGON_API_KEY", "")

# Correct Gold symbol on Polygon
SYMBOL = "C:XAUUSD"


def is_configured():
    """Check if Polygon API key is set"""
    return bool(POLYGON_KEY)


def get_client():
    """Get Polygon client"""
    if not POLYGON_KEY:
        raise ValueError("POLYGON_API_KEY not set in .env file")
    from polygon import RESTClient
    return RESTClient(api_key=POLYGON_KEY)


def get_timeframe_params(timeframe):
    """Convert timeframe to Polygon parameters"""
    mapping = {
        "1m": (1, "minute"),
        "5m": (5, "minute"),
        "15m": (15, "minute"),
        "1H": (1, "hour"),
        "4H": (4, "hour"),
        "D": (1, "day"),
        "W": (1, "week"),
        "M": (1, "month"),
    }
    return mapping.get(timeframe, (1, "day"))


def fetch_historical(timeframe, from_date, to_date):
    """Fetch historical Gold price data from Polygon"""
    if not POLYGON_KEY:
        print("Polygon API key not configured")
        return None

    client = get_client()
    multiplier, timespan = get_timeframe_params(timeframe)

    print(f"Fetching Gold price data from Polygon: {timeframe} ({multiplier} {timespan})")

    try:
        aggs = client.get_aggs(
            ticker=SYMBOL,
            multiplier=multiplier,
            timespan=timespan,
            from_=from_date,
            to=to_date,
            limit=50000
        )

        if not aggs or len(aggs) == 0:
            print(f"No data returned for {timeframe}")
            return None

        data = []
        for agg in aggs:
            data.append({
                "timestamp": datetime.fromtimestamp(agg.timestamp / 1000),
                "open": agg.open,
                "high": agg.high,
                "low": agg.low,
                "close": agg.close,
                "volume": agg.volume
            })

        df = pd.DataFrame(data)
        df["timeframe"] = timeframe
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        print(f"Fetched {len(df)} rows from Polygon")
        return df

    except Exception as e:
        print(f"Polygon fetch failed: {e}")
        return None


def fetch_and_store(timeframe, from_date, to_date):
    """Fetch data and save to database"""
    from database import get_connection

    df = fetch_historical(timeframe, from_date, to_date)
    if df is None or len(df) == 0:
        print(f"No data to save for {timeframe}")
        return None

    try:
        conn = get_connection()
        cur = conn.cursor()
    except Exception as e:
        print(f"Connection error: {e}")
        return None

    inserted = 0
    for _, row in df.iterrows():
        try:
            cur.execute("""
                INSERT INTO gold_ohlcv (timeframe, timestamp, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (timeframe, timestamp) DO UPDATE
                SET open = EXCLUDED.open, high = EXCLUDED.high,
                    low = EXCLUDED.low, close = EXCLUDED.close, volume = EXCLUDED.volume
            """, (
                row["timeframe"], row["timestamp"],
                float(row["open"]), float(row["high"]),
                float(row["low"]), float(row["close"]),
                int(row["volume"]) if pd.notna(row["volume"]) else 0
            ))
            inserted += 1
        except Exception as e:
            continue

    try:
        conn.commit()
    except Exception as e:
        print(f"Commit error: {e}")

    try:
        cur.close()
    except:
        pass

    try:
        conn.close()
    except:
        pass

    print(f"Saved {inserted} new rows to database")
    return df


def fetch_full_history():
    """Fetch all available historical data across timeframes"""
    if not POLYGON_KEY:
        print("Polygon API key required")
        return

    from datetime import date

    end_date = date.today().strftime("%Y-%m-%d")

    print("=" * 50)
    print("FETCHING FULL HISTORY FROM POLYGON")
    print("=" * 50)

    # Daily data
    print("\n[1/4] Daily data...")
    fetch_and_store("D", "2005-01-01", end_date)

    # 4H data
    print("\n[2/4] 4-Hour data...")
    fetch_and_store("4H", "2021-01-01", end_date)

    # 1H data
    print("\n[3/4] 1-Hour data...")
    fetch_and_store("1H", "2024-01-01", end_date)

    # 15m data
    print("\n[4/4] 15-Minute data...")
    fetch_and_store("15m", "2025-01-01", end_date)

    print("\nFull history import complete!")


if __name__ == "__main__":
    if is_configured():
        fetch_full_history()
    else:
        print("Please set POLYGON_API_KEY in .env file")