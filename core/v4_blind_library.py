from __future__ import annotations
from pathlib import Path
import pandas as pd

SYMBOLS = ("GC","SI","ES","NQ","YM","RTY","CL","NG")
TIMEFRAMES = {"15m":"15min","1H":"1h","4H":"4h"}

class BlindHistoricalLibrary:
    """Read-only access to the untouched monthly Databento library."""
    def __init__(self, root=r"C:\TradingPulse\research_data\v4\historical_blind"):
        self.root = Path(root)
        self.raw = self.root / "raw"
        self.canonical = self.root / "canonical_5y"

    def raw_path(self, month, symbol):
        return self.raw / month / f"{symbol}__1m.parquet"

    def canonical_path(self, month, symbol, timeframe):
        return self.canonical / month / f"{symbol}__{timeframe}.parquet"

    @staticmethod
    def _normalize(df):
        out = df.copy()
        if "ts_event" in out.columns:
            out["ts_event"] = pd.to_datetime(out["ts_event"], utc=True)
            out = out.set_index("ts_event")
        elif isinstance(out.index, pd.DatetimeIndex):
            out.index = pd.to_datetime(out.index, utc=True)
        else:
            # Databento parquet created by the recovery bundle normally retains ts_event.
            candidates = [c for c in out.columns if str(c).lower() in ("timestamp","datetime","time","date")]
            if not candidates:
                raise ValueError("No timestamp column/index found")
            out[candidates[0]] = pd.to_datetime(out[candidates[0]], utc=True)
            out = out.set_index(candidates[0])
        out = out.sort_index()
        return out

    def read_raw(self, month, symbol):
        p = self.raw_path(month, symbol)
        if not p.exists():
            raise FileNotFoundError(p)
        return self._normalize(pd.read_parquet(p))

    def read_range(self, symbol, start, end, timeframe="15m"):
        start = pd.Timestamp(start, tz="UTC") if pd.Timestamp(start).tzinfo is None else pd.Timestamp(start).tz_convert("UTC")
        end = pd.Timestamp(end, tz="UTC") if pd.Timestamp(end).tzinfo is None else pd.Timestamp(end).tz_convert("UTC")
        months = pd.period_range(start.tz_localize(None).to_period("M"), end.tz_localize(None).to_period("M"), freq="M")
        parts = []
        for period in months:
            month = str(period)
            p = self.canonical_path(month, symbol, timeframe)
            if p.exists():
                parts.append(self._normalize(pd.read_parquet(p)))
        if not parts:
            return pd.DataFrame()
        df = pd.concat(parts).sort_index()
        return df.loc[(df.index >= start) & (df.index < end)]

    def build_canonical_month(self, month, symbol):
        raw = self.read_raw(month, symbol)
        cols = {str(c).lower(): c for c in raw.columns}
        needed = ("open","high","low","close","volume")
        if not all(k in cols for k in needed):
            raise ValueError(f"{month} {symbol}: missing OHLCV")
        src = raw[[cols[x] for x in needed]].copy()
        src.columns = list(needed)
        outdir = self.canonical / month
        outdir.mkdir(parents=True, exist_ok=True)
        result = {}
        for tf, rule in TIMEFRAMES.items():
            agg = src.resample(rule, label="left", closed="left").agg(
                {"open":"first","high":"max","low":"min","close":"last","volume":"sum"}
            ).dropna(subset=["open","high","low","close"])
            agg["symbol"] = symbol
            p = self.canonical_path(month, symbol, tf)
            agg.reset_index().to_parquet(p, index=False)
            result[tf] = len(agg)
        return result
