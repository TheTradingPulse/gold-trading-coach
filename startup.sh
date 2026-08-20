#!/bin/bash
echo "Creating tables..."
python -c "from core.database import create_tables; create_tables()"
echo "Checking data..."
python -c "
from core.database import get_connection
conn = get_connection()
cur = conn.cursor()
cur.execute(\"SELECT COUNT(*) FROM gold_ohlcv WHERE timeframe = 'D'\")
count = cur.fetchone()[0]
cur.close()
conn.close()
if count < 100:
    print('Importing historical daily data...')
    from core.backtest_engine import import_yahoo_gold_extended
    import_yahoo_gold_extended()
else:
    print(f'Already have {count} daily rows')
print('Fetching intraday data...')
from core.data_engine import fetch_and_store
fetch_and_store('1H', '2y')
fetch_and_store('4H', '2y')
fetch_and_store('15m', '60d')
fetch_and_store('5m', '60d')
print('Intraday data loaded!')
"
echo "Startup complete!"