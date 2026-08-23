from __future__ import annotations
import sqlite3, json, hashlib
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
import pandas as pd

SCHEMA_VERSION = 1
REQUIRED = ("open","high","low","close","volume")

def utc_iso(value):
    ts = pd.Timestamp(value)
    if ts.tzinfo is None: ts = ts.tz_localize("UTC")
    else: ts = ts.tz_convert("UTC")
    return ts.isoformat()

def normalize_candles(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=list(REQUIRED))
    x = df.copy()
    if isinstance(x.columns, pd.MultiIndex):
        x.columns = x.columns.get_level_values(0)
    x = x.rename(columns={c: str(c).lower() for c in x.columns})
    if "timestamp" in x.columns:
        x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True)
        x = x.set_index("timestamp")
    x.index = pd.to_datetime(x.index, utc=True)
    for c in ("open","high","low","close"):
        if c not in x.columns: raise ValueError(f"missing candle column: {c}")
        x[c] = pd.to_numeric(x[c], errors="coerce")
    if "volume" not in x.columns: x["volume"] = 0.0
    x["volume"] = pd.to_numeric(x["volume"], errors="coerce").fillna(0.0)
    x = x[list(REQUIRED)].dropna(subset=["open","high","low","close"])
    x = x[(x["high"] >= x[["open","close","low"]].max(axis=1)) &
          (x["low"] <= x[["open","close","high"]].min(axis=1))]
    x = x[~x.index.duplicated(keep="last")].sort_index()
    x.index.name = "timestamp"
    return x

class MarketWarehouse:
    def __init__(self, path="research_data/v4/market_warehouse.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA foreign_keys=ON")
            yield con
            con.commit()
        finally:
            con.close()

    def _init(self):
        with self.connect() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS warehouse_meta(
              key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS candles(
              symbol TEXT NOT NULL, timeframe TEXT NOT NULL, timestamp TEXT NOT NULL,
              open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
              volume REAL NOT NULL DEFAULT 0, provider TEXT NOT NULL, data_symbol TEXT,
              ingested_at TEXT NOT NULL, PRIMARY KEY(symbol,timeframe,timestamp,provider));
            CREATE INDEX IF NOT EXISTS idx_candles_lookup
              ON candles(symbol,timeframe,timestamp);
            CREATE TABLE IF NOT EXISTS ingestion_runs(
              id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, finished_at TEXT,
              symbol TEXT, timeframe TEXT, provider TEXT, requested_period TEXT,
              rows_received INTEGER DEFAULT 0, rows_written INTEGER DEFAULT 0,
              status TEXT NOT NULL, message TEXT);
            CREATE TABLE IF NOT EXISTS data_quality(
              id INTEGER PRIMARY KEY AUTOINCREMENT, checked_at TEXT NOT NULL,
              symbol TEXT NOT NULL, timeframe TEXT NOT NULL, provider TEXT,
              rows INTEGER NOT NULL, first_ts TEXT, last_ts TEXT, duplicates INTEGER NOT NULL,
              bad_ohlc INTEGER NOT NULL, gap_count INTEGER NOT NULL, details_json TEXT);
            """)
            con.execute("INSERT OR REPLACE INTO warehouse_meta(key,value) VALUES('schema_version',?)",
                        (str(SCHEMA_VERSION),))

    def upsert(self, symbol, timeframe, df, provider="yahoo", data_symbol=None):
        x = normalize_candles(df)
        now = datetime.now(timezone.utc).isoformat()
        rows = [(symbol.upper(), timeframe, utc_iso(idx), float(r.open), float(r.high),
                 float(r.low), float(r.close), float(r.volume), provider, data_symbol, now)
                for idx, r in x.iterrows()]
        if not rows: return 0
        with self.connect() as con:
            con.executemany("""INSERT INTO candles
            (symbol,timeframe,timestamp,open,high,low,close,volume,provider,data_symbol,ingested_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(symbol,timeframe,timestamp,provider) DO UPDATE SET
            open=excluded.open,high=excluded.high,low=excluded.low,close=excluded.close,
            volume=excluded.volume,data_symbol=excluded.data_symbol,ingested_at=excluded.ingested_at""", rows)
        return len(rows)

    def read(self, symbol, timeframe, start=None, end=None, as_of=None, limit=None, provider=None):
        clauses=["symbol=?","timeframe=?"]; args=[symbol.upper(), timeframe]
        if provider: clauses.append("provider=?"); args.append(provider)
        if start: clauses.append("timestamp>=?"); args.append(utc_iso(start))
        cutoff = as_of if as_of is not None else end
        if cutoff: clauses.append("timestamp<=?"); args.append(utc_iso(cutoff))
        sql = "SELECT timestamp,open,high,low,close,volume,provider FROM candles WHERE " + " AND ".join(clauses)
        sql += " ORDER BY timestamp"
        if limit:
            sql = f"SELECT * FROM ({sql} DESC LIMIT {int(limit)}) ORDER BY timestamp"
        with self.connect() as con:
            rows=con.execute(sql,args).fetchall()
        if not rows: return pd.DataFrame(columns=[*REQUIRED,"provider"])
        df=pd.DataFrame([dict(r) for r in rows])
        df["timestamp"]=pd.to_datetime(df["timestamp"],utc=True)
        return df.set_index("timestamp")

    def coverage(self):
        with self.connect() as con:
            rows=con.execute("""SELECT symbol,timeframe,provider,COUNT(*) rows,
            MIN(timestamp) first_ts,MAX(timestamp) last_ts
            FROM candles GROUP BY symbol,timeframe,provider ORDER BY symbol,timeframe,provider""").fetchall()
        return [dict(r) for r in rows]

    def integrity(self):
        with self.connect() as con:
            return con.execute("PRAGMA integrity_check").fetchone()[0]
