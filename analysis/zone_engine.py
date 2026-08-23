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


def _detect_zones(df, zone_type, lookback=5, impulse_factor=2.0):
    """Vectorized equivalent of the legacy supply/demand scan.

    Selection rules, thresholds, bounds, strength math and output schema are
    preserved. Pandas rolling arrays replace tens of thousands of per-row iloc
    operations that dominated MarketState CPU time.
    """
    if len(df) < lookback + 10:
        return []

    work=df.copy()
    body=(work["close"]-work["open"]).abs()
    candle_range=work["high"]-work["low"]
    avg_volume=work["volume"].rolling(window=lookback).mean()

    # Legacy loop used [i-lookback:i], excluding the current candle.
    avg_recent=candle_range.rolling(window=lookback).mean().shift(1)
    zone_high=work["high"].rolling(window=lookback).max().shift(1)
    zone_low=work["low"].rolling(window=lookback).min().shift(1)

    directional=(work["close"] < work["open"]) if zone_type=="supply" else (work["close"] > work["open"])
    body_pct=body.div(candle_range.where(candle_range>0)).fillna(0.0)

    mask=(
        (avg_recent>0)
        & (candle_range > avg_recent*impulse_factor)
        & directional
        & (work["volume"] > avg_volume*1.2)
        & (body_pct>0.5)
        & (zone_low>0)
        & (((zone_high-zone_low)/zone_low*100)<=3.0)
    )

    # Legacy loop starts at lookback + 5.
    eligible=pd.Series(False,index=work.index)
    eligible.iloc[lookback+5:]=True
    positions=np.flatnonzero((mask & eligible).to_numpy())

    zones=[]
    for i in positions:
        ar=float(avg_recent.iloc[i]); av=float(avg_volume.iloc[i])
        cr=float(candle_range.iloc[i]); cv=float(work["volume"].iloc[i])
        strength_val=min(100,int((cr/ar)*25+(cv/av)*25)) if av>0 else 50
        zones.append({
            "type":zone_type,
            "upper_bound":float(zone_high.iloc[i]),
            "lower_bound":float(zone_low.iloc[i]),
            "created_at":str(work.index[i]),
            "freshness_score":100,
            "retest_count":0,
            "strength":strength_val,
        })
    return zones


def detect_supply_zones(df, lookback=5, impulse_factor=2.0):
    """Detect supply zones (resistance areas)."""
    return _detect_zones(df,"supply",lookback=lookback,impulse_factor=impulse_factor)


def detect_demand_zones(df, lookback=5, impulse_factor=2.0):
    """Detect demand zones (support areas)."""
    return _detect_zones(df,"demand",lookback=lookback,impulse_factor=impulse_factor)


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
        for z in active_supply[-3:]: print(f"   Zone: ${z['lower_bound']:.2f} - ${z['upper_bound']:.2f} | Created: {z['created_at'][:16]}")
    if active_demand:
        print(f"\nActive Demand Zones (within 1%):")
        for z in active_demand[-3:]: print(f"   Zone: ${z['lower_bound']:.2f} - ${z['upper_bound']:.2f} | Created: {z['created_at'][:16]}")
    if not active_supply and not active_demand: print("\nNo active zones near current price")
    print(f"\n--- Recent Supply Zones (last 3) ---")
    for z in supply_zones[-3:]: print(f"  ${z['lower_bound']:.2f} - ${z['upper_bound']:.2f} | {z['created_at'][:16]} | Strength: {z['strength']}")
    print(f"\n--- Recent Demand Zones (last 3) ---")
    for z in demand_zones[-3:]: print(f"  ${z['lower_bound']:.2f} - ${z['upper_bound']:.2f} | {z['created_at'][:16]} | Strength: {z['strength']}")


def scan_all_timeframes():
    """Run zone analysis on strategic and tactical timeframes"""
    timeframes = ["D", "4H", "1H", "15m"]
    for tf in timeframes:
        analyze_zones(tf); print("\n" + "=" * 60)


if __name__ == "__main__":
    scan_all_timeframes()
