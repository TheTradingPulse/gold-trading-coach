"""
Railway deployment startup script
- Creates tables if needed
- Imports initial data if database is empty
"""
from core.database import create_tables, get_connection

print("=" * 50)
print("GOLD TRADING COACH - Railway Startup")
print("=" * 50)

# Create tables
create_tables()

# Check if data exists
conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM gold_ohlcv")
count = cur.fetchone()[0]
cur.close()
conn.close()

if count == 0:
    print("No data found. Importing historical data...")
    from core.backtest_engine import import_yahoo_gold_extended
    import_yahoo_gold_extended()
else:
    print(f"Database has {count} rows. Skipping import.")

print("Startup complete!")