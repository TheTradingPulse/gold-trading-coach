import pandas as pd
import numpy as np
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
from database import DB_PASSWORD
import psycopg2


def load_data(timeframe, limit=500):
    """Load OHLCV data from database"""
    from database import get_connection
    conn = get_connection()

    query = """
        SELECT timestamp, open, high, low, close, volume
        FROM gold_ohlcv
        WHERE timeframe = %s
        ORDER BY timestamp DESC
        LIMIT %s;
    """

    df = pd.read_sql_query(query, conn, params=(timeframe, limit))
    conn.close()

    df = df.set_index("timestamp")
    df = df.sort_index()
    return df

def detect_supply_zones(df, lookback=5, impulse_factor=2.0):
    """Detect supply zones (resistance areas). OPTIMIZED with volume & body confirmation."""
    if len(df) < lookback + 10:
        return []

    zones = []
    df = df.copy()

    df["body"] = abs(df["close"] - df["open"])
    df["range"] = df["high"] - df["low"]
    df["avg_range"] = df["range"].rolling(window=lookback).mean()
    df["avg_volume"] = df["volume"].rolling(window=lookback).mean()

    for i in range(lookback + 5, len(df)):
        recent_ranges = df["range"].iloc[i - lookback : i]
        avg_recent = recent_ranges.mean()
        
        if avg_recent <= 0:
            continue

        current_range = df["range"].iloc[i]
        current_volume = df["volume"].iloc[i]
        avg_vol = df["avg_volume"].iloc[i]
        is_bearish = df["close"].iloc[i] < df["open"].iloc[i]
        body_pct = df["body"].iloc[i] / current_range if current_range > 0 else 0

        if (current_range > avg_recent * impulse_factor
            and is_bearish
            and current_volume > avg_vol * 1.2
            and body_pct > 0.5):

            zone_high = df["high"].iloc[i - lookback : i].max()
            zone_low = df["low"].iloc[i - lookback : i].min()

            zone_width = (zone_high - zone_low) / zone_low * 100 if zone_low > 0 else 0
            if zone_width > 3.0:
                continue

            strength_val = min(100, int((current_range / avg_recent) * 25 + (current_volume / avg_vol) * 25)) if avg_vol > 0 else 50

            zone = {
                "type": "supply",
                "upper_bound": float(zone_high),
                "lower_bound": float(zone_low),
                "created_at": str(df.index[i]),
                "freshness_score": 100,
                "retest_count": 0,
                "strength": strength_val
            }
            zones.append(zone)

    return zones


def detect_demand_zones(df, lookback=5, impulse_factor=2.0):
    """Detect demand zones (support areas). OPTIMIZED with volume & body confirmation."""
    if len(df) < lookback + 10:
        return []

    zones = []
    df = df.copy()

    df["body"] = abs(df["close"] - df["open"])
    df["range"] = df["high"] - df["low"]
    df["avg_range"] = df["range"].rolling(window=lookback).mean()
    df["avg_volume"] = df["volume"].rolling(window=lookback).mean()

    for i in range(lookback + 5, len(df)):
        recent_ranges = df["range"].iloc[i - lookback : i]
        avg_recent = recent_ranges.mean()
        
        if avg_recent <= 0:
            continue

        current_range = df["range"].iloc[i]
        current_volume = df["volume"].iloc[i]
        avg_vol = df["avg_volume"].iloc[i]
        is_bullish = df["close"].iloc[i] > df["open"].iloc[i]
        body_pct = df["body"].iloc[i] / current_range if current_range > 0 else 0

        if (current_range > avg_recent * impulse_factor
            and is_bullish
            and current_volume > avg_vol * 1.2
            and body_pct > 0.5):

            zone_high = df["high"].iloc[i - lookback : i].max()
            zone_low = df["low"].iloc[i - lookback : i].min()

            zone_width = (zone_high - zone_low) / zone_low * 100 if zone_low > 0 else 0
            if zone_width > 3.0:
                continue

            strength_val = min(100, int((current_range / avg_recent) * 25 + (current_volume / avg_vol) * 25)) if avg_vol > 0 else 50

            zone = {
                "type": "demand",
                "upper_bound": float(zone_high),
                "lower_bound": float(zone_low),
                "created_at": str(df.index[i]),
                "freshness_score": 100,
                "retest_count": 0,
                "strength": strength_val
            }
            zones.append(zone)

    return zones


def is_price_near_zone(current_price, zone, tolerance_pct=0.5):
    """Check if price is near a zone within tolerance percentage"""
    zone_mid = (zone["upper_bound"] + zone["lower_bound"]) / 2
    if zone_mid <= 0:
        return False
    distance_pct = abs(current_price - zone_mid) / current_price * 100
    return distance_pct <= tolerance_pct


def analyze_zones(timeframe="1H"):
    """Full zone analysis for a timeframe"""
    df = load_data(timeframe, limit=500)
    if df is None or len(df) < 10:
        print(f"Not enough data for {timeframe}")
        return

    current_price = df["close"].iloc[-1]

    supply_zones = detect_supply_zones(df)
    demand_zones = detect_demand_zones(df)

    print(f"\n=== Zone Analysis - {timeframe} Timeframe ===")
    print(f"Current Price: ${current_price:.2f}")
    print(f"Total Supply Zones Found: {len(supply_zones)}")
    print(f"Total Demand Zones Found: {len(demand_zones)}")

    active_supply = [z for z in supply_zones if is_price_near_zone(current_price, z, 1.0)]
    active_demand = [z for z in demand_zones if is_price_near_zone(current_price, z, 1.0)]

    if active_supply:
        print(f"\nActive Supply Zones (within 1%):")
        for z in active_supply[-3:]:
            print(f"   Zone: ${z['lower_bound']:.2f} - ${z['upper_bound']:.2f} | Created: {z['created_at'][:16]}")

    if active_demand:
        print(f"\nActive Demand Zones (within 1%):")
        for z in active_demand[-3:]:
            print(f"   Zone: ${z['lower_bound']:.2f} - ${z['upper_bound']:.2f} | Created: {z['created_at'][:16]}")

    if not active_supply and not active_demand:
        print("\nNo active zones near current price")

    print(f"\n--- Recent Supply Zones (last 3) ---")
    for z in supply_zones[-3:]:
        print(f"  ${z['lower_bound']:.2f} - ${z['upper_bound']:.2f} | {z['created_at'][:16]} | Strength: {z['strength']}")

    print(f"\n--- Recent Demand Zones (last 3) ---")
    for z in demand_zones[-3:]:
        print(f"  ${z['lower_bound']:.2f} - ${z['upper_bound']:.2f} | {z['created_at'][:16]} | Strength: {z['strength']}")


def scan_all_timeframes():
    """Run zone analysis on strategic and tactical timeframes"""
    timeframes = ["D", "4H", "1H", "15m"]

    for tf in timeframes:
        analyze_zones(tf)
        print("\n" + "=" * 60)


if __name__ == "__main__":
    scan_all_timeframes()