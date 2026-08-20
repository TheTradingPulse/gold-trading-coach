"""
Gold Trading Coach Data Engine
Uses Yahoo Finance GC=F (continuous front-month COMEX Gold futures)
Provides live and historical data for the system.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from datetime import date, timedelta


def is_live_available():
    """Yahoo Finance GC=F is always available (delayed 15 min but correct futures)."""
    return True


def fetch_latest_data():
    """Fetch latest GC=F data from Yahoo Finance and save to database."""
    from data_engine import fetch_and_store

    try:
        print("Fetching latest GC=F data from Yahoo Finance...")
        # 1-minute data (last 7 days)
        fetch_and_store("1m", "7d")
        # 5-minute data (last 60 days)
        fetch_and_store("5m", "60d")
        # 15-minute data (last 60 days)
        fetch_and_store("15m", "60d")
        # 1-hour data (last 2 years)
        fetch_and_store("1H", "2y")
        # 4-hour data (resampled from 1H, handled in fetch_and_store)
        fetch_and_store("4H", "2y")
        # Daily data (max available)
        fetch_and_store("D", "max")
        print("Latest GC=F data fetch complete.")
        return True
    except Exception as e:
        print(f"Data fetch failed: {e}")
        return False


def quick_refresh():
    """Lightweight refresh for bot commands. Fetches only recent data."""
    from data_engine import fetch_and_store

    try:
        print("Quick refresh of GC=F data...")
        # Fetch only last 2 days for 1m, 5m, 15m, and a small recent slice for 1H
        fetch_and_store("1m", "7d")
        fetch_and_store("5m", "60d")
        fetch_and_store("15m", "60d")
        fetch_and_store("1H", "2y")
        print("Quick refresh complete.")
        return True
    except Exception as e:
        print(f"Quick refresh failed: {e}")
        return False


def get_data_source_name():
    """Return the data source name for display."""
    return "Yahoo Finance GC=F (COMEX Front-Month Futures)"