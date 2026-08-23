from __future__ import annotations
from datetime import datetime, timezone
import pandas as pd
import yfinance as yf
from instruments import get_instrument
from v4_market_warehouse import MarketWarehouse, normalize_candles
from v4_data_quality import audit_frame

YF_INTERVAL={"1m":"1m","5m":"5m","15m":"15m","30m":"30m","1H":"1h","4H":"1h","D":"1d","W":"1wk"}
YF_PERIOD={"1m":"7d","5m":"60d","15m":"60d","30m":"60d","1H":"730d","4H":"730d","D":"10y","W":"10y"}

def fetch_yahoo(symbol,timeframe,period=None):
    inst=get_instrument(symbol)
    tf=str(timeframe)
    interval=YF_INTERVAL[tf]
    period=period or YF_PERIOD[tf]
    raw=yf.download(inst.data_symbol,period=period,interval=interval,progress=False,auto_adjust=False)
    x=normalize_candles(raw)
    if tf=="4H" and not x.empty:
        x=x.resample("4h",origin="start_day").agg(
            {"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()
    return x, inst.data_symbol, period

def collect(symbol,timeframe,warehouse_path="research_data/v4/market_warehouse.db",period=None):
    wh=MarketWarehouse(warehouse_path)
    started=datetime.now(timezone.utc).isoformat()
    run_id=None
    with wh.connect() as con:
        cur=con.execute("""INSERT INTO ingestion_runs(started_at,symbol,timeframe,provider,requested_period,status)
                           VALUES(?,?,?,?,?,?)""",(started,symbol.upper(),timeframe,"yahoo",period,"RUNNING"))
        run_id=cur.lastrowid
    try:
        df,data_symbol,requested=fetch_yahoo(symbol,timeframe,period)
        audit=audit_frame(df,timeframe)
        written=wh.upsert(symbol,timeframe,df,"yahoo",data_symbol)
        finished=datetime.now(timezone.utc).isoformat()
        with wh.connect() as con:
            con.execute("""UPDATE ingestion_runs SET finished_at=?,requested_period=?,rows_received=?,
                           rows_written=?,status='PASS',message=? WHERE id=?""",
                        (finished,requested,len(df),written,"reference/development data",run_id))
            con.execute("""INSERT INTO data_quality
            (checked_at,symbol,timeframe,provider,rows,first_ts,last_ts,duplicates,bad_ohlc,gap_count,details_json)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (finished,symbol.upper(),timeframe,"yahoo",audit["rows"],audit["first_ts"],audit["last_ts"],
             audit["duplicates"],audit["bad_ohlc"],audit["gap_count"],__import__("json").dumps(audit)))
        return {"symbol":symbol.upper(),"timeframe":timeframe,"rows":len(df),"written":written,
                "first":audit["first_ts"],"last":audit["last_ts"],"gaps":audit["gap_count"],"status":"PASS"}
    except Exception as exc:
        with wh.connect() as con:
            con.execute("UPDATE ingestion_runs SET finished_at=?,status='FAIL',message=? WHERE id=?",
                        (datetime.now(timezone.utc).isoformat(),str(exc),run_id))
        return {"symbol":symbol.upper(),"timeframe":timeframe,"status":"FAIL","error":str(exc)}

def collect_universe(symbols=("GC","SI","ES","NQ","YM","RTY","CL","NG"),
                     timeframes=("1m","5m","15m","30m","1H","4H","D","W"),
                     warehouse_path="research_data/v4/market_warehouse.db"):
    return [collect(s,tf,warehouse_path) for s in symbols for tf in timeframes]
