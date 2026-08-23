web: bash startup.sh web && streamlit run dashboard.py --server.port=$PORT --server.address=0.0.0.0
worker: bash startup.sh worker && python core/telegram_bot.py
