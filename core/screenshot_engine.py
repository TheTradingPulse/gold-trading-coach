import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "analysis"))
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import mplfinance as mpf
import os
from datetime import datetime


SCREENSHOT_DIR = Path(__file__).parent.parent / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)


def load_chart_data(timeframe, limit=100):
    """Load data formatted for mplfinance"""
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

    if len(df) == 0:
        return None

    df = df.sort_values("timestamp")
    df = df.set_index("timestamp")
    df.index = pd.DatetimeIndex(df.index)
    df.columns = ["Open", "High", "Low", "Close", "Volume"]

    return df


def capture_chart(timeframe, limit=100, filename=None):
    """Capture a single chart screenshot"""
    df = load_chart_data(timeframe, limit)

    if df is None or len(df) < 5:
        print(f"Not enough data for {timeframe}")
        return None

    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"gold_{timeframe}_{timestamp}.png"

    filepath = SCREENSHOT_DIR / filename

    mc = mpf.make_marketcolors(up='green', down='red', edge='inherit', wick='inherit', volume='in')
    s = mpf.make_mpf_style(marketcolors=mc, gridstyle=':', y_on_right=False, base_mpf_style='charles')

    sma_20 = df["Close"].rolling(window=20).mean()
    sma_50 = df["Close"].rolling(window=50).mean()

    apds = [
        mpf.make_addplot(sma_20, color='blue', width=0.7, label='SMA 20'),
        mpf.make_addplot(sma_50, color='orange', width=0.7, label='SMA 50')
    ]

    fig, axes = mpf.plot(df, type='candle', style=s, title=f'Gold Futures (GC) - {timeframe}',
                         ylabel='Price ($)', volume=True, addplot=apds,
                         returnfig=True, figsize=(12, 7), savefig=filepath)

    print(f"Chart saved: {filepath}")
    return str(filepath)


def capture_trade_setup(timeframes=None):
    """Capture charts for all key timeframes"""
    if timeframes is None:
        timeframes = ["D", "1H", "15m", "5m", "1m"]

    files = []
    for tf in timeframes:
        filepath = capture_chart(tf, limit=100)
        if filepath:
            files.append(filepath)

    return files


def capture_all_and_zip():
    """Capture all timeframes and return list of files"""
    timeframes = ["D", "1H", "15m", "5m", "1m"]
    files = capture_trade_setup(timeframes)

    if files:
        print(f"\nCaptured {len(files)} charts:")
        for f in files:
            print(f"  - {f}")

    return files


if __name__ == "__main__":
    capture_all_and_zip()