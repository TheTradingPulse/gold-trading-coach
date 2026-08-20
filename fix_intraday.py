import os
from datetime import date, timedelta

os.environ["DATABASE_URL"] = "postgresql://postgres:iAwDrcIkfdLpbjScbZlhaqNEcbcbPWIF@hayabusa.proxy.rlwy.net:57737/railway"

import psycopg2
import sys
sys.path.insert(0, "core")

from polygon_engine import fetch_and_store

# Delete only wrong intraday data
conn = psycopg2.connect(os.environ["DATABASE_URL"])
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