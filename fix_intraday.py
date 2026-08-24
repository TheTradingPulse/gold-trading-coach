import os
from datetime import date, timedelta
import psycopg2
import sys
sys.path.insert(0, "core")

from polygon_engine import fetch_and_store

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required. Credentials must never be embedded in source code.")
if os.getenv("ALLOW_DATA_RESET") != "YES":
    raise RuntimeError("Destructive maintenance blocked. Set ALLOW_DATA_RESET=YES explicitly.")

# Delete only wrong intraday data
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
for tf in ["15m", "1H", "4H"]:
    cur.execute("DELETE FROM gold_ohlcv WHERE timeframe = %s", (tf,))
conn.commit()
cur.close()
conn.close()
print("Deleted old 15m, 1H, and 4H data")

# Import correct recent intraday data
end = date.today().strftime("%Y-%m-%d")
start = (date.today() - timedelta(days=5)).strftime("%Y-%m-%d")

fetch_and_store("15m", start, end)
fetch_and_store("1H", start, end)
fetch_and_store("4H", start, end)

print("Intraday data fixed with XAUUSD")
