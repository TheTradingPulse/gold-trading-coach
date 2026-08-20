import yfinance as yf
import pandas as pd

print("Fetching Gold Futures data...")

gold = yf.download("GC=F", period="1mo", interval="1h")

print(f"Got {len(gold)} rows of data")
print("\nLast 5 rows:")
print(gold.tail())

gold.to_csv("gold_data.csv")
print("\nSaved to gold_data.csv")