import os
import sys
from datetime import date, timedelta

os.environ["DATABASE_URL"] = "postgresql://postgres:iAwDrcIkfdLpbjScbZlhaqNEcbcbPWIF@hayabusa.proxy.rlwy.net:57737/railway"

import psycopg2
sys.path.insert(0, "core")
from data_engine import fetch_and_store

print("Deleting old price data from Railway database...")
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute("DELETE FROM gold_ohlcv")
conn.commit()
cur.close()
conn.close()
print("Old data deleted.")

print("Importing GC=F front-month Gold futures data...")

fetch_and_store("D", "max")
fetch_and_store("4H", "2y")
fetch_and_store("1H", "2y")

print("GC=F data import complete.")