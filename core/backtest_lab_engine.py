"""Trading Pulse V3.2A - Backtest Lab + Evidence Warehouse.

User-initiated research uses the same canonical point-in-time detector as system
research. Results are persisted to PostgreSQL as evidence; duplicate historical
observations are de-duplicated and linked to many runs.
"""
from __future__ import annotations
import json, uuid
from datetime import datetime, timezone, timedelta
from typing import Iterable
from database import get_connection
from historical_acquisition import acquire
from historical_data_store import HistoricalStore
from canonical_replay_adapter import detector_for_backtest
from historical_backtest_engine import run_point_in_time_backtest, summarize

ENGINE_VERSION = "3.2A"
SCORING_VERSION = "canonical-production"
EVIDENCE_SOURCE = "USER_BACKTEST"

TF_SETS = {
    "5m": ["5m"], "15m": ["15m"], "1H": ["1H"], "4H": ["4H"], "Daily": ["D"],
    "15m+": ["15m", "1H", "4H", "D"],
    "1H+": ["1H", "4H", "D"],
    "4H+": ["4H", "D"],
}

def ensure_evidence_schema():
    conn=get_connection(); cur=conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS backtest_runs(
      run_id VARCHAR(64) PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      source VARCHAR(32) NOT NULL, engine_version VARCHAR(32) NOT NULL,
      scoring_version VARCHAR(64) NOT NULL, symbol VARCHAR(16) NOT NULL,
      timeframe_scope VARCHAR(32) NOT NULL, min_score DOUBLE PRECISION NOT NULL,
      direction VARCHAR(8) NOT NULL, lookback_days INTEGER NOT NULL,
      status VARCHAR(20) NOT NULL, parameters_json TEXT, summary_json TEXT,
      error_text TEXT)
    """)
    cur.execute("""CREATE TABLE IF NOT EXISTS setup_observations(
      observation_key VARCHAR(255) PRIMARY KEY, symbol VARCHAR(16) NOT NULL,
      timeframe VARCHAR(16) NOT NULL, setup_timestamp TIMESTAMPTZ NOT NULL,
      candidate_id VARCHAR(160) NOT NULL, score DOUBLE PRECISION NOT NULL,
      side VARCHAR(8) NOT NULL, entry DOUBLE PRECISION, stop DOUBLE PRECISION,
      target DOUBLE PRECISION, outcome VARCHAR(24), r_multiple DOUBLE PRECISION,
      bars_to_resolution INTEGER, engine_version VARCHAR(32) NOT NULL,
      scoring_version VARCHAR(64) NOT NULL, first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW())
    """)
    cur.execute("""CREATE TABLE IF NOT EXISTS backtest_run_observations(
      run_id VARCHAR(64) REFERENCES backtest_runs(run_id) ON DELETE CASCADE,
      observation_key VARCHAR(255) REFERENCES setup_observations(observation_key) ON DELETE CASCADE,
      PRIMARY KEY(run_id, observation_key))
    """)
    conn.commit(); cur.close(); conn.close()

def _obs_key(e):
    return f"{ENGINE_VERSION}|{e.symbol}|{e.timeframe}|{e.timestamp}|{e.candidate_id}"

def _create_run(run_id,symbol,scope,min_score,direction,days,params):
    ensure_evidence_schema(); conn=get_connection(); cur=conn.cursor()
    cur.execute("""INSERT INTO backtest_runs(run_id,source,engine_version,scoring_version,symbol,timeframe_scope,min_score,direction,lookback_days,status,parameters_json)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'RUNNING',%s)""",
                (run_id,EVIDENCE_SOURCE,ENGINE_VERSION,SCORING_VERSION,symbol,scope,min_score,direction,days,json.dumps(params)))
    conn.commit(); cur.close(); conn.close()

def _finish_run(run_id,status,summary=None,error=None):
    conn=get_connection(); cur=conn.cursor()
    cur.execute("UPDATE backtest_runs SET status=%s,summary_json=%s,error_text=%s WHERE run_id=%s",
                (status,json.dumps(summary) if summary is not None else None,error,run_id))
    conn.commit(); cur.close(); conn.close()

def _persist_events(run_id,events):
    if not events: return 0
    conn=get_connection(); cur=conn.cursor(); n=0
    for e in events:
        k=_obs_key(e)
        cur.execute("""INSERT INTO setup_observations(observation_key,symbol,timeframe,setup_timestamp,candidate_id,score,side,entry,stop,target,outcome,r_multiple,bars_to_resolution,engine_version,scoring_version)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT(observation_key) DO NOTHING""",
                    (k,e.symbol,e.timeframe,e.timestamp,e.candidate_id,e.score,e.side,e.entry,e.stop,e.target,e.outcome,e.r_multiple,e.bars_to_resolution,ENGINE_VERSION,SCORING_VERSION))
        cur.execute("""INSERT INTO backtest_run_observations(run_id,observation_key) VALUES(%s,%s)
                       ON CONFLICT DO NOTHING""",(run_id,k)); n+=1
    conn.commit(); cur.close(); conn.close(); return n

def _period_for(tf,days):
    if tf in ("5m","15m"): return "60d"
    if tf in ("1H","4H"): return "730d"
    return "2y"

def run_lab_backtest(symbol:str, timeframe_scope:str, min_score:float=9.4,
                     direction:str="BOTH", lookback_days:int=90,
                     store_root="research_data/history", warmup_bars:int=250,
                     forward_bars:int=100):
    symbol=str(symbol).upper(); direction=str(direction).upper()
    tfs=TF_SETS.get(timeframe_scope,[timeframe_scope])
    params={"symbol":symbol,"timeframes":tfs,"minimum_score":float(min_score),
            "direction":direction,"lookback_days":int(lookback_days),
            "warmup_bars":warmup_bars,"forward_bars":forward_bars}
    run_id=uuid.uuid4().hex; _create_run(run_id,symbol,timeframe_scope,min_score,direction,lookback_days,params)
    all_events=[]; per_tf={}; errors={}
    try:
        store=HistoricalStore(store_root)
        cutoff=datetime.now(timezone.utc)-timedelta(days=int(lookback_days))
        for tf in tfs:
            try:
                acquire(symbol,tf,store_root=store_root,period=_period_for(tf,lookback_days))
                hist=store.load(symbol,tf)
                if len(hist): hist=hist.loc[hist.index>=cutoff]
                if len(hist)<=warmup_bars+1:
                    per_tf[tf]={"error":f"insufficient history ({len(hist)} rows)"}; continue
                events=run_point_in_time_backtest(symbol,tf,hist,detector_for_backtest,
                                                   warmup_bars=warmup_bars,forward_bars=forward_bars)
                events=[e for e in events if float(e.score)>=float(min_score) and
                        (direction=="BOTH" or str(e.side).upper()==direction)]
                _persist_events(run_id,events); all_events.extend(events); per_tf[tf]=summarize(events)
            except Exception as exc:
                errors[tf]=str(exc); per_tf[tf]={"error":str(exc)}
        overall=summarize(all_events)
        overall.update({"run_id":run_id,"symbol":symbol,"scope":timeframe_scope,
                        "minimum_score":float(min_score),"direction":direction,
                        "lookback_days":int(lookback_days),"timeframes":per_tf,
                        "errors":errors,"evidence_rows":len(all_events)})
        overall.update(_analytics(all_events))
        _finish_run(run_id,"COMPLETE",overall); return overall
    except Exception as exc:
        _finish_run(run_id,"FAILED",None,str(exc)); raise


def _analytics(events):
    rows=[e.to_dict() if hasattr(e,"to_dict") else dict(e) for e in events]
    resolved=[r for r in rows if r.get("outcome") in ("TARGET","STOP")]
    wins=[r for r in resolved if r.get("outcome")=="TARGET"]
    losses=[r for r in resolved if r.get("outcome")=="STOP"]
    open_count=sum(1 for r in rows if r.get("outcome") in ("OPEN","NOT_ENTERED"))
    rs=[float(r["r_multiple"]) for r in resolved if r.get("r_multiple") is not None]
    pos=sum(r for r in rs if r>0); neg=abs(sum(r for r in rs if r<0))
    equity=0.0; peak=0.0; max_dd=0.0
    for r in rs:
        equity += r; peak=max(peak,equity); max_dd=min(max_dd,equity-peak)
    grades={}
    for r in rows:
        score=float(r.get("score",0)); bucket=f"{int(score)}-{int(score)+1}" if score<9 else "9-10"
        grades[bucket]=grades.get(bucket,0)+1
    monthly={}
    for r in resolved:
        try: month=str(r.get("timestamp",""))[:7]
        except Exception: month=""
        if month: monthly[month]=monthly.get(month,0.0)+float(r.get("r_multiple") or 0.0)
    return {
        "profit_factor": round(pos/neg,2) if neg else (None if not pos else 999.0),
        "max_drawdown_r": round(max_dd,2),
        "total_r": round(sum(rs),2) if rs else None,
        "wins": len(wins), "losses": len(losses), "unresolved": open_count,
        "grade_distribution": grades,
        "monthly_r": {k:round(v,2) for k,v in sorted(monthly.items())},
    }

def recent_experiments(limit:int=5):
    ensure_evidence_schema(); conn=get_connection(); cur=conn.cursor()
    cur.execute("""SELECT run_id,created_at,symbol,timeframe_scope,min_score,direction,lookback_days,status,summary_json
                   FROM backtest_runs ORDER BY created_at DESC LIMIT %s""",(int(limit),))
    cols=["run_id","created_at","symbol","scope","min_score","direction","days","status","summary_json"]
    out=[]
    for row in cur.fetchall():
        d=dict(zip(cols,row)); raw=d.pop("summary_json",None)
        try: d["summary"]=json.loads(raw) if raw else {}
        except Exception: d["summary"]={}
        out.append(d)
    cur.close(); conn.close(); return out

def evidence_stats():
    ensure_evidence_schema(); conn=get_connection(); cur=conn.cursor()
    cur.execute("SELECT COUNT(*) FROM backtest_runs WHERE status='COMPLETE'"); runs=int(cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM setup_observations"); obs=int(cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM setup_observations WHERE outcome IN ('TARGET','STOP')"); resolved=int(cur.fetchone()[0])
    cur.close(); conn.close(); return {"runs":runs,"observations":obs,"resolved":resolved}
