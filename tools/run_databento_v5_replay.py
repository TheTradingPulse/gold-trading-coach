from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SYMBOLS = ("GC", "SI", "ES", "NQ", "YM", "RTY", "CL", "NG")
TICKS = {"GC": .1, "SI": .005, "ES": .25, "NQ": .25, "YM": 1., "RTY": .1, "CL": .01, "NG": .001}
PROVIDER = "databento_v5"
SCHEMA = "TP_DATABENTO_V5_REPLAY_1"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def wilson_lower(wins: int, total: int, z: float = 1.959963984540054) -> float | None:
    if total <= 0:
        return None
    p = wins / total
    d = 1 + z * z / total
    return (p + z * z / (2 * total) - z * math.sqrt((p * (1-p) + z*z/(4*total))/total)) / d


def read_tf(con, symbol, tf):
    q = """SELECT timestamp,open,high,low,close,volume FROM candles
           WHERE symbol=? AND timeframe=? AND provider=? ORDER BY timestamp"""
    x = pd.read_sql_query(q, con, params=(symbol, tf, PROVIDER))
    x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True)
    return x.set_index("timestamp")


def normalize_raw(path):
    x = pd.read_parquet(path)
    low = {str(c).lower(): c for c in x.columns}
    if "ts_event" in low:
        x = x.set_index(low["ts_event"])
    elif not isinstance(x.index, pd.DatetimeIndex):
        c = next((low[k] for k in ("timestamp", "datetime", "time", "date") if k in low), None)
        if c is None:
            raise ValueError(f"No timestamp in {path}")
        x = x.set_index(c)
    x.index = pd.to_datetime(x.index, utc=True)
    low = {str(c).lower(): c for c in x.columns}
    x = x[[low[k] for k in ("open", "high", "low", "close")]]
    x.columns = ["open", "high", "low", "close"]
    return x.sort_index()[~x.index.duplicated(keep="last")]


def load_raw(root, symbol):
    files = sorted((root / "research_data/v4/historical_blind/raw").glob(f"*/{symbol}__1m.parquet"))
    if len(files) != 60:
        raise RuntimeError(f"{symbol}: expected 60 one-minute files, found {len(files)}")
    x = pd.concat([normalize_raw(p) for p in files]).sort_index()
    return x[~x.index.duplicated(keep="last")]


def atr(frame, n=14):
    prev = frame.close.shift(1)
    tr = pd.concat([(frame.high-frame.low), (frame.high-prev).abs(), (frame.low-prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n).mean()


def prior_asof(series, ts):
    pos = series.index.searchsorted(ts, side="right") - 1
    return float(series.iloc[pos]) if pos >= 0 and pd.notna(series.iloc[pos]) else None


def generate_candidates(symbol, m15, h1, h4, daily):
    tick = TICKS[symbol]
    x = m15.copy()
    x["atr"] = atr(x)
    x["body_ratio"] = (x.close-x.open).abs() / (x.high-x.low).replace(0, np.nan)
    d = daily.copy(); d["atr"] = atr(d)
    h1_ma = h1.close.rolling(20, min_periods=20).mean()
    h4_ma = h4.close.rolling(20, min_periods=20).mean()
    rows = []
    # Base candle followed by a completed three-bar departure. Detection uses no future data beyond i+3.
    for i in range(30, len(x)-3):
        base = x.iloc[i]
        if not np.isfinite(base.atr) or not np.isfinite(base.body_ratio) or base.body_ratio > .55:
            continue
        dep = x.iloc[i+1:i+4]
        up = float(dep.high.max()-base.high)
        down = float(base.low-dep.low.min())
        direction = "LONG" if up >= base.atr and up > down else ("SHORT" if down >= base.atr and down > up else None)
        if direction is None:
            continue
        detected = x.index[i+3]
        daily_atr = prior_asof(d.atr, detected)
        if not daily_atr or daily_atr <= 0:
            continue
        if direction == "LONG":
            entry, stop = float(base.high), float(base.low-tick)
            strength = min(2., up/base.atr)
        else:
            entry, stop = float(base.low), float(base.high+tick)
            strength = min(2., down/base.atr)
        risk = abs(entry-stop)
        risk_atr = risk/daily_atr
        min_ticks = risk/tick
        executable = min_ticks >= 4 and .015 <= risk_atr <= .35
        ma1, ma4 = prior_asof(h1_ma, detected), prior_asof(h4_ma, detected)
        c1, c4 = prior_asof(h1.close, detected), prior_asof(h4.close, detected)
        trend_known = all(v is not None for v in (ma1,ma4,c1,c4))
        trend_aligned = int(trend_known and ((direction=="LONG" and c1>ma1 and c4>ma4) or
                                            (direction=="SHORT" and c1<ma1 and c4<ma4)))
        rows.append({
            "candidate_id": hashlib.sha256(f"{symbol}|{detected.isoformat()}|{direction}|{entry:.10f}".encode()).hexdigest()[:24],
            "symbol": symbol, "detected_at": detected.isoformat(), "base_at": x.index[i].isoformat(),
            "direction": direction, "entry": entry, "stop": stop,
            "target_3r": entry + (3*risk if direction=="LONG" else -3*risk),
            "target_5r": entry + (5*risk if direction=="LONG" else -5*risk),
            "risk": risk, "risk_ticks": min_ticks, "risk_daily_atr": risk_atr,
            "departure_strength": strength, "base_body_ratio": float(base.body_ratio),
            "trend_known": int(trend_known), "trend_aligned": trend_aligned,
            "execution_eligible": int(executable),
            "execution_reason": "eligible" if executable else ("stop_below_4_ticks" if min_ticks < 4 else "stop_outside_atr_band"),
        })
    return rows


def replay(rows, raw, max_minutes=14400):
    idx = raw.index
    hi = raw.high.to_numpy(float); lo = raw.low.to_numpy(float)
    counts = {"not_entered":0,"stop_first":0,"target_3r_first":0,"same_minute_ambiguous":0,"open":0}
    for n, r in enumerate(rows, 1):
        start = idx.searchsorted(pd.Timestamp(r["detected_at"]), side="right")
        end = min(len(idx), start+max_minutes)
        entered = None
        for j in range(start, end):
            if lo[j] <= r["entry"] <= hi[j]: entered=j; break
        if entered is None:
            r.update(outcome="not_entered", entered_at=None, resolved_at=None); counts["not_entered"] += 1; continue
        r["entered_at"] = idx[entered].isoformat(); outcome="open"; resolved=None
        for j in range(entered, end):
            stop = lo[j] <= r["stop"] if r["direction"]=="LONG" else hi[j] >= r["stop"]
            target = hi[j] >= r["target_3r"] if r["direction"]=="LONG" else lo[j] <= r["target_3r"]
            # OHLC cannot establish whether entry preceded another level inside the entry minute.
            if j == entered and (stop or target): outcome="same_minute_ambiguous"; resolved=j; break
            if stop and target: outcome="same_minute_ambiguous"; resolved=j; break
            if stop: outcome="stop_first"; resolved=j; break
            if target: outcome="target_3r_first"; resolved=j; break
        r["outcome"]=outcome; r["resolved_at"]=idx[resolved].isoformat() if resolved is not None else None
        counts[outcome] += 1
        if n % 5000 == 0: print(f"  replayed {n:,}/{len(rows):,} candidates", flush=True)
    return counts


def init_db(path):
    con=sqlite3.connect(path)
    con.execute("DROP TABLE IF EXISTS candidates")
    con.execute("""CREATE TABLE candidates(
      candidate_id TEXT PRIMARY KEY,symbol TEXT,detected_at TEXT,base_at TEXT,direction TEXT,
      entry REAL,stop REAL,target_3r REAL,target_5r REAL,risk REAL,risk_ticks REAL,risk_daily_atr REAL,
      departure_strength REAL,base_body_ratio REAL,trend_known INTEGER,trend_aligned INTEGER,
      execution_eligible INTEGER,execution_reason TEXT,outcome TEXT,entered_at TEXT,resolved_at TEXT)""")
    con.execute("CREATE INDEX idx_v5_candidates ON candidates(symbol,detected_at,outcome)")
    return con


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="."); ap.add_argument("--max-minutes",type=int,default=14400)
    a=ap.parse_args(); root=Path(a.root).resolve(); v5=root/"research_data/v5"
    warehouse=v5/"databento_v5_warehouse.db"; manifest=v5/"databento_v5_warehouse_manifest.json"
    if not warehouse.exists() or not manifest.exists(): raise SystemExit("V5 warehouse or manifest missing")
    m=json.loads(manifest.read_text(encoding="utf-8"))
    if not m.get("ready") or m.get("integrity") != "ok" or m.get("provider") != PROVIDER: raise SystemExit("V5 manifest is not ready")
    out=v5/"replay"; out.mkdir(parents=True,exist_ok=True); db=out/"databento_v5_evidence.db"
    dst=init_db(db); src=sqlite3.connect(warehouse)
    report={"schema":SCHEMA,"generated_utc":utc_now(),"provider":PROVIDER,"warehouse_manifest":str(manifest),"symbols":{}}
    cols=[r[1] for r in dst.execute("PRAGMA table_info(candidates)")]
    for symbol in SYMBOLS:
        print(f"\n{symbol}: generating point-in-time candidates",flush=True)
        frames={tf:read_tf(src,symbol,tf) for tf in ("15m","1H","4H","D")}
        rows=generate_candidates(symbol,frames["15m"],frames["1H"],frames["4H"],frames["D"])
        print(f"  generated {len(rows):,}; loading authoritative one-minute bars",flush=True)
        raw=load_raw(root,symbol); counts=replay(rows,raw,a.max_minutes)
        dst.executemany(f"INSERT INTO candidates VALUES({','.join('?' for _ in cols)})", [[r.get(c) for c in cols] for r in rows]); dst.commit()
        eligible=[r for r in rows if r["execution_eligible"]]
        resolved=[r for r in eligible if r["outcome"] in ("stop_first","target_3r_first")]
        wins=sum(r["outcome"]=="target_3r_first" for r in resolved)
        report["symbols"][symbol]={"candidates":len(rows),"execution_eligible":len(eligible),"outcomes":counts,
          "eligible_resolved":len(resolved),"eligible_3r_wins":wins,"eligible_3r_rate":wins/len(resolved) if resolved else None,
          "eligible_3r_wilson_lower":wilson_lower(wins,len(resolved))}
        print(f"  outcomes: {counts}",flush=True)
    src.close(); dst.execute("PRAGMA optimize"); dst.commit()
    integrity=dst.execute("PRAGMA integrity_check").fetchone()[0]; dst.close()
    report["integrity"]=integrity; report["status"]="evidence_ready_for_calibration" if integrity=="ok" else "failed"
    rp=out/"databento_v5_replay_report.json"; rp.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(f"\nEVIDENCE READY: {db}"); print(f"REPORT READY: {rp}"); print(f"INTEGRITY: {integrity}")


if __name__=="__main__": main()
