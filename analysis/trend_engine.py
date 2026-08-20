import pandas as pd
import numpy as np
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
from database import DB_PASSWORD
import psycopg2


def load_data(timeframe, limit=200):
    """Load OHLCV data from database"""
    from database import get_connection
    conn = get_connection()

    query = """
        SELECT timestamp, open, high, low, close, volume
        FROM gold_ohlcv
        WHERE timeframe = %s
        ORDER BY timestamp ASC
        LIMIT %s;
    """

    df = pd.read_sql_query(query, conn, params=(timeframe, limit))
    conn.close()

    df = df.set_index("timestamp")
    return df


def calculate_sma(df, period=50):
    """Calculate Simple Moving Average"""
    return df["close"].rolling(window=period).mean()


def calculate_ema(df, period=50):
    """Calculate Exponential Moving Average"""
    return df["close"].ewm(span=period, adjust=False).mean()


def assess_trend(df):
    """
    Determine trend direction for a single timeframe.
    
    Uses 3 methods:
    1. Price vs 50 SMA (position)
    2. 50 SMA slope (momentum)
    3. Higher highs/lows over last 20 candles (structure)
    
    Returns: 'bullish', 'bearish', or 'neutral'
    """
    if len(df) < 50:
        return "neutral"

    df = df.copy()
    df["sma_50"] = calculate_sma(df, 50)
    df["sma_50_slope"] = df["sma_50"].diff(20)

    # 1. Price position relative to SMA
    price = df["close"].iloc[-1]
    sma = df["sma_50"].iloc[-1]
    price_above = price > sma

    # 2. SMA slope
    slope_up = df["sma_50_slope"].iloc[-1] > 0

    # 3. Structure - higher highs/higher lows for bullish
    last_20 = df.iloc[-20:]
    highs_rising = last_20["high"].iloc[-1] > last_20["high"].iloc[:10].max()
    lows_rising = last_20["low"].iloc[-1] > last_20["low"].iloc[:10].min()

    # Structure - lower highs/lower lows for bearish
    highs_falling = last_20["high"].iloc[-1] < last_20["high"].iloc[:10].min()
    lows_falling = last_20["low"].iloc[-1] < last_20["low"].iloc[:10].max()

    # Scoring
    bullish_score = 0
    bearish_score = 0

    if price_above:
        bullish_score += 1
    else:
        bearish_score += 1

    if slope_up:
        bullish_score += 1
    else:
        bearish_score += 1

    if highs_rising and lows_rising:
        bullish_score += 1
    elif highs_falling and lows_falling:
        bearish_score += 1

    if bullish_score >= 2:
        return "bullish"
    elif bearish_score >= 2:
        return "bearish"
    else:
        return "neutral"


def analyze_all_timeframes():
    """
    Analyze trend for every timeframe.
    Returns dict with trend and alignment score.
    """
    timeframes = ["M", "W", "D", "4H", "1H", "15m", "5m", "1m"]
    trends = {}

    print("=== Multi-Timeframe Trend Analysis ===\n")

    for tf in timeframes:
        df = load_data(tf, limit=200)
        if df is not None and len(df) >= 50:
            trend = assess_trend(df)
            trends[tf] = trend
            emoji = "🟢" if trend == "bullish" else "🔴" if trend == "bearish" else "⚪"
            print(f"{emoji} {tf:4s} → {trend}")
        else:
            trends[tf] = "no_data"
            print(f"⚪ {tf:4s} → no data (need to fetch first)")

    # Calculate alignment score
    strategic_tfs = ["M", "W", "D"]
    tactical_tfs = ["4H", "1H", "15m"]
    execution_tfs = ["5m", "1m"]

    print("\n=== Trend Summary ===")

    # Strategic alignment
    strategic_trends = [trends.get(tf) for tf in strategic_tfs if trends.get(tf) not in [None, "neutral", "no_data"]]
    if strategic_trends:
        strategic_direction = max(set(strategic_trends), key=strategic_trends.count)
        strategic_score = strategic_trends.count(strategic_direction) / len(strategic_trends) * 100
        print(f"Strategic (M/W/D): {strategic_direction.upper()} ({strategic_score:.0f}%)")

    # Overall alignment
    all_trends = [trends.get(tf) for tf in timeframes if trends.get(tf) not in [None, "neutral", "no_data"]]
    if all_trends:
        dominant = max(set(all_trends), key=all_trends.count)
        alignment = all_trends.count(dominant) / len(all_trends) * 100
        print(f"Overall Alignment: {dominant.upper()} ({alignment:.0f}%)")

    return trends


if __name__ == "__main__":
    analyze_all_timeframes()