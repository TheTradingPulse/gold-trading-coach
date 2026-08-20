"""
Gold Trading Coach - Trade Engine
Provides price, trend, alignment, and setup grading.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from database import get_connection
from zone_engine import load_data


def get_current_price():
    """
    Get the most recent Gold price.
    Falls back from 1m to 5m, 15m, 1H, 4H, and D if needed.
    """
    for tf in ["1m", "5m", "15m", "1H", "4H", "D"]:
        try:
            conn = get_connection()
            query = """
                SELECT close, timestamp
                FROM gold_ohlcv
                WHERE timeframe = %s
                ORDER BY timestamp DESC
                LIMIT 1
            """
            df = pd.read_sql_query(query, conn, params=(tf,))
            conn.close()
            if len(df) > 0:
                price = float(df["close"].iloc[0])
                if pd.notna(price) and price > 0:
                    return price
        except Exception:
            continue
    return None


def get_trends():
    """
    Return trend for all key timeframes.
    """
    from trend_engine import assess_trend
    timeframes = ["M", "W", "D", "4H", "1H", "15m", "5m", "1m"]
    trends = {}

    for tf in timeframes:
        try:
            df = load_data(tf, limit=200)
            if df is not None and len(df) >= 50:
                trends[tf] = assess_trend(df)
            else:
                trends[tf] = "no_data"
        except Exception:
            trends[tf] = "no_data"

    return trends


def calculate_alignment(trends):
    """
    Calculate alignment score and direction from trends dict.
    """
    if not trends:
        return "neutral", 0

    valid = [t for t in trends.values() if t in ("bullish", "bearish")]
    if not valid:
        return "neutral", 0

    bullish = valid.count("bullish")
    bearish = valid.count("bearish")

    if bullish > bearish:
        direction = "bullish"
        score = (bullish / len(valid)) * 100
    elif bearish > bullish:
        direction = "bearish"
        score = (bearish / len(valid)) * 100
    else:
        direction = "neutral"
        score = 50

    return direction, round(score, 1)


def grade_setup(alignment, zone_strength):
    """
    Grade a setup from A+ to Avoid.
    """
    score = 0

    if alignment >= 90:
        score += 40
    elif alignment >= 75:
        score += 30
    elif alignment >= 60:
        score += 20

    if zone_strength >= 80:
        score += 40
    elif zone_strength >= 60:
        score += 30
    elif zone_strength >= 40:
        score += 20
    else:
        score += 10

    if score >= 70:
        return "A+"
    elif score >= 60:
        return "A"
    elif score >= 45:
        return "B"
    elif score >= 30:
        return "C"
    else:
        return "Avoid"