#!/bin/bash
set -e

MODE="${1:-web}"

echo "========================================"
echo " TRADING PULSE STARTUP"
echo " MODE: ${MODE}"
echo "========================================"

echo ""
echo "[1/2] Creating/verifying PostgreSQL tables..."
python -c "from core.database import create_tables; create_tables()"

if [ "$MODE" != "worker" ]; then
    echo ""
    echo "[2/2] Web startup: historical refresh skipped."
    echo "Historical maintenance is worker-owned."
    echo ""
    echo "========================================"
    echo " TRADING PULSE WEB STARTUP COMPLETE"
    echo "========================================"
    exit 0
fi

echo ""
echo "[2/2] Worker-owned historical maintenance..."

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
print('Worker historical market data refresh complete.')
"

echo ""
echo "========================================"
echo " TRADING PULSE WORKER STARTUP COMPLETE"
echo "========================================"
