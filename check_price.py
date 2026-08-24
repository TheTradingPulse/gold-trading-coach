import os
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required. Credentials must never be embedded in source code.")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

for tf in ["1m", "5m", "15m", "1H", "4H", "D"]:
    cur.execute("""
        SELECT close, timestamp
        FROM gold_ohlcv
        WHERE timeframe = %s
        ORDER BY timestamp DESC
        LIMIT 1
    """, (tf,))
    row = cur.fetchone()
    if row:
        print(f"{tf}: {row[0]} at {row[1]}")
    else:
        print(f"{tf}: no data")

cur.close()
conn.close()
