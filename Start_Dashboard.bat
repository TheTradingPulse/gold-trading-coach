@echo off
title Gold Trading Coach - Dashboard
cd /d "C:\Users\owner\OneDrive\Desktop\PROJECTS FOR CLIENTS\gold-trading-coach"
call venv\Scripts\activate
echo.
echo ========================================
echo   Gold Trading Coach Dashboard
echo ========================================
echo.
echo Starting web dashboard...
echo Opening in your browser shortly...
echo.
start http://localhost:8501
streamlit run dashboard.py
pause