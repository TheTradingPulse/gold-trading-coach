"""Trading Pulse V3.3A live/paper journal tracker.

Snapshots proposed setups without changing them, then resolves them from market
OHLCV.  This is evidence collection, not broker execution.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

from database import get_connection
from market_state_builder import load_market_data
from instruments import get_instrument

TRACKER_VERSION = "3.3C"


def ensure_tracking_schema():
    conn = get_connection(); cur = conn.cursor()
    additions = [
        ("candidate_id", "VARCHAR(64)"), ("timeframe", "VARCHAR(10)"),
        ("setup_score", "DOUBLE PRECISION"), ("source", "VARCHAR(30) DEFAULT 'LIVE_PAPER'"),
        ("tracking_status", "VARCHAR(20) DEFAULT 'PENDING_ENTRY'"),
        ("entry_triggered_at", "TIMESTAMPTZ"), ("resolved_at", "TIMESTAMPTZ"),
        ("highest_target", "INTEGER DEFAULT 0"), ("target2", "DOUBLE PRECISION"),
        ("r_multiple", "DOUBLE PRECISION"), ("engine_version", "VARCHAR(30)"),
    ]
    for name, ddl in additions:
        cur.execute(f"ALTER TABLE trade_journal ADD COLUMN IF NOT EXISTS {name} {ddl}")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trade_journal_tracking ON trade_journal(tracking_status, symbol, timeframe)")
    conn.commit(); cur.close(); conn.close()


def _score10(score: Any) -> float:
    try:
        x=float(score)
        return round(x/10.0 if x>10 else x, 2)
    except Exception: return 0.0


def add_candidate_to_journal(candidate, plan: dict, engine_version: str = "3.3C", source: str = "LIVE_PAPER") -> tuple[int, bool]:
    """Immutable snapshot of the selected proposed setup. Returns (id, created)."""
    ensure_tracking_schema()
    entry=plan.get("entry"); stop=plan.get("stop"); t1=plan.get("t1"); t2=plan.get("t2")
    if entry is None or stop is None or t1 is None:
        raise ValueError("Setup needs entry, stop and Target 1 before it can be tracked.")
    symbol=str(getattr(candidate,"symbol","GC") or "GC").upper()
    direction="LONG" if str(getattr(candidate,"zone_type","")).lower()=="demand" else "SHORT"
    candidate_id=str(getattr(candidate,"candidate_id","") or "")
    timeframe=str(getattr(candidate,"timeframe","") or "")
    score=_score10(getattr(candidate,"setup_score",0))
    rr=float(plan.get("rr1") or 0)
    grade=str(getattr(candidate,"grade","--") or "--")
    alignment=100.0 if bool(getattr(candidate,"trend_aligned",False)) else 0.0
    zone_type=str(getattr(candidate,"zone_type","") or "")
    source = str(source or "LIVE_PAPER").upper()
    if source not in {"LIVE_PAPER", "ELITE_AUTO"}:
        raise ValueError(f"Unsupported journal source: {source}")
    notes=f"V3.3C paper-tracked proposed setup; immutable snapshot; source={source}; lifecycle={getattr(candidate,'lifecycle','--')}"
    conn=get_connection(); cur=conn.cursor()
    # Elite auto-capture is immutable evidence: once a specific candidate/plan has
    # been captured, never create it again on Streamlit reruns. Manual paper
    # tracking retains the prior unresolved-only de-duplication behavior.
    status_clause = "" if source == "ELITE_AUTO" else "AND COALESCE(tracking_status,'') IN ('PENDING_ENTRY','OPEN')"
    cur.execute(f"""SELECT id FROM trade_journal WHERE candidate_id=%s AND symbol=%s AND timeframe=%s
                   AND entry=%s AND stop=%s AND target=%s AND COALESCE(source,'LIVE_PAPER')=%s
                   {status_clause}
                   ORDER BY id DESC LIMIT 1""", (candidate_id,symbol,timeframe,float(entry),float(stop),float(t1),source))
    row=cur.fetchone()
    if row:
        cur.close(); conn.close(); return int(row[0]), False
    cur.execute("""INSERT INTO trade_journal
        (timestamp,symbol,direction,entry,stop,target,target2,rr_ratio,grade,alignment_score,zone_type,
         outcome,notes,candidate_id,timeframe,setup_score,source,tracking_status,engine_version)
        VALUES (NOW(),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'OPEN',%s,%s,%s,%s,%s,'PENDING_ENTRY',%s)
        RETURNING id""", (symbol,direction,float(entry),float(stop),float(t1),float(t2) if t2 is not None else None,
                            rr,grade,alignment,zone_type,notes,candidate_id,timeframe,score,source,engine_version))
    trade_id=int(cur.fetchone()[0]); conn.commit(); cur.close(); conn.close(); return trade_id, True


def _frame_since(symbol: str, timeframe: str, since, limit: int = 2000):
    tf=timeframe if timeframe in {"1m","5m","15m","1H","4H","D","W","M"} else "1H"
    df=load_market_data(tf, limit=limit, symbol=symbol)
    if df is None or len(df)==0: return df
    df=df.copy(); df.columns=[str(c).lower() for c in df.columns]
    try:
        import pandas as pd
        idx=pd.to_datetime(df.index, utc=True, errors="coerce")
        stamp=pd.Timestamp(since)
        stamp=stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
        df=df.loc[idx >= stamp]
    except Exception: pass
    return df


def refresh_tracked_trades() -> dict:
    """Resolve pending/open paper trades from candles. Same-bar ambiguity is STOP-first."""
    ensure_tracking_schema(); conn=get_connection(); cur=conn.cursor()
    cur.execute("""SELECT id,timestamp,symbol,direction,entry,stop,target,target2,timeframe,tracking_status
                   FROM trade_journal WHERE COALESCE(source,'') IN ('LIVE_PAPER','ELITE_AUTO')
                   AND COALESCE(tracking_status,'') IN ('PENDING_ENTRY','OPEN') ORDER BY id""")
    rows=cur.fetchall(); checked=updated=0; errors=[]
    for row in rows:
        trade_id,created,symbol,direction,entry,stop,t1,t2,tf,status=row
        checked+=1
        try:
            df=_frame_since(symbol,tf,created)
            if df is None or len(df)==0: continue
            active=(status=="OPEN"); entry_time=None; highest=0; resolved=None; exit_price=None; outcome=None; r_mult=None
            risk=abs(float(entry)-float(stop))
            for ts,bar in df.iterrows():
                lo=float(bar["low"]); hi=float(bar["high"])
                if not active:
                    if lo <= float(entry) <= hi:
                        active=True; entry_time=ts
                    else: continue
                # Conservative policy: if stop and target touch same candle, stop wins.
                stop_hit = lo <= float(stop) if direction=="LONG" else hi >= float(stop)
                t1_hit = hi >= float(t1) if direction=="LONG" else lo <= float(t1)
                t2_hit = False if t2 is None else (hi >= float(t2) if direction=="LONG" else lo <= float(t2))
                if stop_hit:
                    outcome="LOSS"; resolved=ts; exit_price=float(stop); r_mult=-1.0; break
                if t2_hit:
                    highest=2; outcome="WIN"; resolved=ts; exit_price=float(t2)
                    r_mult=abs(float(t2)-float(entry))/risk if risk else None; break
                if t1_hit:
                    highest=max(highest,1); outcome="WIN"; resolved=ts; exit_price=float(t1)
                    r_mult=abs(float(t1)-float(entry))/risk if risk else None; break
            if outcome:
                point_value=get_instrument(symbol).point_value
                pnl_points=(exit_price-float(entry)) if direction=="LONG" else (float(entry)-exit_price)
                pnl=pnl_points*point_value
                cur.execute("""UPDATE trade_journal SET tracking_status='RESOLVED',outcome=%s,exit_price=%s,pnl=%s,
                               r_multiple=%s,highest_target=%s,resolved_at=%s,
                               entry_triggered_at=COALESCE(entry_triggered_at,%s) WHERE id=%s""",
                            (outcome,exit_price,pnl,r_mult,highest,resolved,entry_time,trade_id)); updated+=1
            elif active:
                cur.execute("""UPDATE trade_journal SET tracking_status='OPEN',entry_triggered_at=COALESCE(entry_triggered_at,%s),
                               highest_target=GREATEST(COALESCE(highest_target,0),%s) WHERE id=%s""", (entry_time,highest,trade_id)); updated+=1
        except Exception as exc: errors.append(f"#{trade_id}: {exc}")
    conn.commit(); cur.close(); conn.close()
    return {"checked":checked,"updated":updated,"errors":errors}
