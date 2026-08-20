"""
Gold Trading Coach - Data Engine
Fetches and stores Gold Futures (GC=F) data using Yahoo Finance.
Uses batch insert to be fast and avoid connection drops.
"""
import yfinance as yf
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from database import get_connection

SYMBOL = "GC=F"

TIMEFRAMES = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1H": "1h",
    "4H": "1h",  # 4H is resampled from 1H
    "D": "1d",
    "W": "1wk",
    "M": "1mo",
}


def fetch_gold_data(timeframe="1H", period="2y"):
    """Fetch Gold Futures data from Yahoo Finance."""
    yf_tf = TIMEFRAMES.get(timeframe, "1d")

    print(f"Fetching Gold Futures ({SYMBOL}) - {timeframe} timeframe...")
    try:
        df = yf.download(SYMBOL, period=period, interval=yf_tf, progress=False)
    except Exception as e:
        print(f"Yahoo download failed for {timeframe}: {e}")
        return None

    if df is None or df.empty:
        print(f"No data returned for {timeframe}")
        return None

    df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    })

    df.index.name = "timestamp"
    df = df.reset_index()
    df["timeframe"] = timeframe

    try:
        if df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")
        else:
            df["timestamp"] = df["timestamp"].dt.tz_convert("UTC")
    except Exception:
        pass

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    print(f"Fetched {len(df)} rows")
    return df


def fetch_4h_data(period="2y"):
    """Fetch 1H data and resample into 4H candles."""
    df = fetch_gold_data("1H", period)
    if df is None:
        return None

    df = df.set_index("timestamp")

    df_4h = df.resample("4h").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna()

    df_4h = df_4h.reset_index()
    df_4h["timeframe"] = "4H"
    df_4h["timestamp"] = pd.to_datetime(df_4h["timestamp"], utc=True)
    print(f"Resampled to {len(df_4h)} 4H candles")
    return df_4h


def save_to_database(df):
    """Save dataframe to PostgreSQL using fast batch insert."""
    if df is None or len(df) == 0:
        print("No data to save")
        return False

    # Prepare rows
    rows = []
    for _, row in df.iterrows():
        rows.append((
            str(row["timeframe"]),
            row["timestamp"],
            float(row["open"]) if pd.notna(row["open"]) else None,
            float(row["high"]) if pd.notna(row["high"]) else None,
            float(row["low"]) if pd.notna(row["low"]) else None,
            float(row["close"]) if pd.notna(row["close"]) else None,
            float(row["volume"]) if pd.notna(row["volume"]) else 0,
        ))

    try:
        conn = get_connection()
        cur = conn.cursor()

        execute_values(
            cur,
            """
            INSERT INTO gold_ohlcv
                (timeframe, timestamp, open, high, low, close, volume)
            VALUES %s
            ON CONFLICT (timeframe, timestamp) DO UPDATE
            SET open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume
            """,
            rows,
            template="(%s, %s, %s, %s, %s, %s, %s)",
            page_size=500
        )

        conn.commit()
        cur.close()
        conn.close()
        print(f"Saved {len(rows)} rows to database")
        return True

    except Exception as e:
        print(f"Database save error: {e}")
        try:
            cur.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass
        return False


def load_from_database(timeframe="1H", limit=100):
    """Load data from PostgreSQL into DataFrame."""
    try:
        conn = get_connection()
        query = """
            SELECT timestamp, open, high, low, close, volume
            FROM gold_ohlcv
            WHERE timeframe = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """
        df = pd.read_sql_query(query, conn, params=(timeframe, limit))
        conn.close()
        if len(df) == 0:
            return None
        df = df.sort_values("timestamp")
        df = df.set_index("timestamp")
        return df
    except Exception as e:
        print(f"Load error for {timeframe}: {e}")
        return None


def fetch_and_store(timeframe="1H", period="2y"):
    """Fetch data and save to database in one step."""
    if timeframe == "4H":
        df = fetch_4h_data(period)
    else:
        df = fetch_gold_data(timeframe, period)

    if df is None:
        print(f"No data for {timeframe}, skipping.")
        return None

    save_to_database(df)
    return df


if __name__ == "__main__":
    fetch_and_store("D", "max")
    fetch_and_store("4H", "2y")
    fetch_and_store("1H", "2y")