@echo off
setlocal
title The Trading Pulse - Local Dashboard
cd /d C:\TradingPulse

echo Starting PostgreSQL container...
docker start tradingpulse-postgres >nul 2>&1

if not exist .venv\Scripts\python.exe (
    echo ERROR: C:\TradingPulse\.venv is missing.
    echo Create it with: python -m venv .venv
    pause
    exit /b 1
)

set DB_HOST=localhost
set DB_PORT=5432
set DB_NAME=gold_trading
set DB_USER=postgres
if not defined DB_PASSWORD set DB_PASSWORD=postgres

echo Verifying database tables...
.venv\Scripts\python.exe -c "from core.database import create_tables; create_tables()"
if errorlevel 1 (
    echo ERROR: Database initialization failed.
    pause
    exit /b 1
)

echo Opening The Trading Pulse at http://localhost:8501
start "" http://localhost:8501
.venv\Scripts\python.exe -m streamlit run dashboard.py
pause
