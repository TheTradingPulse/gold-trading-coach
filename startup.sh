#!/bin/bash
set -e

echo "========================================"
echo " TRADING PULSE V2.5.1 STARTUP"
echo "========================================"

echo ""
echo "[1/3] Creating/verifying PostgreSQL tables..."
python -c "from core.database import create_tables; create_tables()"

echo ""
echo "[2/3] Checking historical database..."
python -c "
from core.database import get_connection

conn = get_connection()
cur = conn.cursor()
cur.execute(\"SELECT COUNT(*) FROM gold_ohlcv WHERE timeframe = 'D'\")
count = cur.fetchone()[0]
cur.close()
conn.close()

print(f'Existing daily candles: {count}')

if count < 100:
    print('Importing extended Gold daily history...')
    from core.backtest_engine import import_yahoo_gold_extended
    import_yahoo_gold_extended()
else:
    print('Historical daily database already initialized.')
"

echo ""
echo "[3/3] Updating V2.5.1 MarketState timeframes..."
python -c "
from core.data_engine import fetch_and_store

jobs = [
    ('M', 'max'),
    ('W', 'max'),
    ('D', 'max'),
    ('4H', '2y'),
    ('1H', '2y'),
    ('15m', '60d'),
    ('5m', '60d'),
    ('1m', '7d'),
]

for timeframe, period in jobs:
    print()
    print(f'Updating {timeframe}...')
    try:
        fetch_and_store(timeframe, period)
    except Exception as exc:
        print(f'WARNING: {timeframe} update failed: {exc}')

print()
print('V2.5.1 market data refresh complete.')
"

echo ""
echo "========================================"
echo " TRADING PULSE STARTUP COMPLETE"
echo "========================================"
