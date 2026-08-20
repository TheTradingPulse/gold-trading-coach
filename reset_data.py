import os
from datetime import date, timedelta

os.environ["DATABASE_URL"] = "postgresql://postgres:iAwDrcIkfdLpbjScbZlhaqNEcbcbPWIF@hayabusa.proxy.rlwy.net:57737/railway"

import psycopg2
import sys
sys.path.insert(0, "core")

from polygon_engine import fetch_and_store, fetch_full_history

# 1. Delete all old price data
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute("DELETE FROM gold_ohlcv")
conn.commit()
cur.close()
conn.close()
print("Deleted old price data")

# 2. Import full XAUUSD history (Daily, 4H, 1H, 15m)
fetch_full_history()

# 3. Import recent 1m and 5m data
end = date.today().strftime("%Y-%m-%d")
start = (date.today() - timedelta(days=3)).strftime("%Y-%m-%d")
fetch_and_store("1m", start, end)
fetch_and_store("5m", start, end)

print("Database reset complete with XAUUSD data")