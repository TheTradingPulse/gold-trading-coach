"""The Trading Pulse V2.10E - active Yahoo development-feed adapter."""

def is_live_available():
    """Backward-compatible name. True means the Yahoo adapter is available, NOT real-time."""
    return True


def is_realtime_available():
    return False


def fetch_latest_data():
    from data_engine import fetch_and_store
    try:
        print("Fetching latest Yahoo GC=F data (DELAYED / DEVELOPMENT FEED)...")
        fetch_and_store("1m","7d"); fetch_and_store("5m","60d"); fetch_and_store("15m","60d")
        fetch_and_store("1H","2y"); fetch_and_store("4H","2y"); fetch_and_store("D","max")
        print("Yahoo GC=F refresh complete."); return True
    except Exception as e:
        print(f"Data fetch failed: {e}"); return False


def quick_refresh():
    from data_engine import fetch_and_store
    try:
        print("Quick refresh Yahoo GC=F (DELAYED / DEVELOPMENT FEED)...")
        fetch_and_store("1m","7d"); fetch_and_store("5m","60d"); fetch_and_store("15m","60d"); fetch_and_store("1H","2y")
        print("Quick refresh complete."); return True
    except Exception as e:
        print(f"Quick refresh failed: {e}"); return False


def get_data_source_name():
    return "Yahoo Finance GC=F (DELAYED / Continuous Front Month)"


def get_data_source_metadata():
    return {"source":"Yahoo Finance","symbol":"GC=F","contract_mode":"CONTINUOUS_FRONT_MONTH","realtime":False,"execution_eligible":False,"expected_delay_minutes":15}
