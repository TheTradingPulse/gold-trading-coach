"""Trading Pulse V3.4 Pass 4 - Backtest Lab / historical evidence warehouse."""
from __future__ import annotations
import json, uuid
from datetime import datetime, timezone, timedelta
from database import get_connection
from historical_acquisition import acquire
from historical_data_store import HistoricalStore
from historical_opportunity_research import replay_timeframe, summarize, ENGINE_VERSION

SCORING_VERSION="V3.4E-shared-opportunity-policy"; EVIDENCE_SOURCE="USER_BACKTEST"
TF_SETS={"15m":["15m"],"1H":["1H"],"4H":["4H"],"Daily":["D"],"15m+":["15m","1H","4H","D"],"1H+":["1H","4H","D"],"4H+":["4H","D"]}
REPLAY_CONTEXT=("15m","1H","4H","D","5m")

def ensure_evidence_schema():
    conn=get_connection(); cur=conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS backtest_runs(run_id VARCHAR(64) PRIMARY KEY,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),source VARCHAR(32) NOT NULL,engine_version VARCHAR(32) NOT NULL,scoring_version VARCHAR(64) NOT NULL,symbol VARCHAR(16) NOT NULL,timeframe_scope VARCHAR(32) NOT NULL,min_score DOUBLE PRECISION NOT NULL,direction VARCHAR(8) NOT NULL,lookback_days INTEGER NOT NULL,status VARCHAR(20) NOT NULL,parameters_json TEXT,summary_json TEXT,error_text TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS setup_observations(observation_key VARCHAR(255) PRIMARY KEY,symbol VARCHAR(16) NOT NULL,timeframe VARCHAR(16) NOT NULL,setup_timestamp TIMESTAMPTZ NOT NULL,candidate_id VARCHAR(160) NOT NULL,score DOUBLE PRECISION NOT NULL,side VARCHAR(8) NOT NULL,entry DOUBLE PRECISION,stop DOUBLE PRECISION,target DOUBLE PRECISION,outcome VARCHAR(24),r_multiple DOUBLE PRECISION,bars_to_resolution INTEGER,engine_version VARCHAR(32) NOT NULL,scoring_version VARCHAR(64) NOT NULL,first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    cur.execute("""CREATE TABLE IF NOT EXISTS backtest_run_observations(run_id VARCHAR(64) REFERENCES backtest_runs(run_id) ON DELETE CASCADE,observation_key VARCHAR(255) REFERENCES setup_observations(observation_key) ON DELETE CASCADE,PRIMARY KEY(run_id,observation_key))""")
    extras={"tier":"VARCHAR(12)","composite_score":"DOUBLE PRECISION","projected_rr":"DOUBLE PRECISION","lifecycle":"VARCHAR(24)","zone_quality":"DOUBLE PRECISION","freshness":"DOUBLE PRECISION","retests":"INTEGER","mtf_aligned":"INTEGER","mtf_total":"INTEGER","mtf_ratio":"DOUBLE PRECISION","confirmations":"INTEGER","distance_percent":"DOUBLE PRECISION","mae_r":"DOUBLE PRECISION","mfe_r":"DOUBLE PRECISION"}
    for col,typ in extras.items(): cur.execute(f"ALTER TABLE setup_observations ADD COLUMN IF NOT EXISTS {col} {typ}")
    conn.commit(); cur.close(); conn.close()

def _obs_key(e): return f"{ENGINE_VERSION}|{e.symbol}|{e.timeframe}|{e.timestamp}|{e.candidate_id}"
def _create_run(run_id,symbol,scope,min_score,direction,days,params):
    ensure_evidence_schema(); conn=get_connection(); cur=conn.cursor(); cur.execute("""INSERT INTO backtest_runs(run_id,source,engine_version,scoring_version,symbol,timeframe_scope,min_score,direction,lookback_days,status,parameters_json) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'RUNNING',%s)""",(run_id,EVIDENCE_SOURCE,ENGINE_VERSION,SCORING_VERSION,symbol,scope,min_score,direction,days,json.dumps(params))); conn.commit(); cur.close(); conn.close()
def _finish_run(run_id,status,summary=None,error=None):
    conn=get_connection(); cur=conn.cursor(); cur.execute("UPDATE backtest_runs SET status=%s,summary_json=%s,error_text=%s WHERE run_id=%s",(status,json.dumps(summary) if summary is not None else None,error,run_id)); conn.commit(); cur.close(); conn.close()
def _persist_events(run_id,events):
    if not events:return 0
    conn=get_connection(); cur=conn.cursor(); n=0
    for e in events:
        k=_obs_key(e); d=e.to_dict()
        cur.execute("""INSERT INTO setup_observations(observation_key,symbol,timeframe,setup_timestamp,candidate_id,score,side,entry,stop,target,outcome,r_multiple,bars_to_resolution,engine_version,scoring_version,tier,composite_score,projected_rr,lifecycle,zone_quality,freshness,retests,mtf_aligned,mtf_total,mtf_ratio,confirmations,distance_percent,mae_r,mfe_r) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(observation_key) DO NOTHING""",(k,e.symbol,e.timeframe,e.timestamp,e.candidate_id,e.score,e.side,e.entry,e.stop,e.target,e.outcome,e.r_multiple,e.bars_to_resolution,ENGINE_VERSION,SCORING_VERSION,e.tier,e.composite_score,e.projected_rr,e.lifecycle,e.zone_quality,e.freshness,e.retests,e.mtf_aligned,e.mtf_total,e.mtf_ratio,e.confirmations,e.distance_percent,e.mae_r,e.mfe_r))
        cur.execute("INSERT INTO backtest_run_observations(run_id,observation_key) VALUES(%s,%s) ON CONFLICT DO NOTHING",(run_id,k)); n+=1
    conn.commit(); cur.close(); conn.close(); return n

def _period_for(tf,days):
    if tf in ("5m","15m"):return "60d"
    if tf in ("1H","4H"):return "730d"
    return "2y"

def run_lab_backtest(symbol:str,timeframe_scope:str,min_score:float=8.5,direction:str="BOTH",lookback_days:int=90,store_root="research_data/history",warmup_bars:int=250,forward_bars:int=100):
    symbol=str(symbol).upper(); direction=str(direction).upper(); eval_tfs=TF_SETS.get(timeframe_scope,[timeframe_scope])
    params={"symbol":symbol,"timeframes":eval_tfs,"minimum_score":float(min_score),"direction":direction,"lookback_days":int(lookback_days),"warmup_bars":warmup_bars,"forward_bars":forward_bars,"policy":"V3.4E"}
    run_id=uuid.uuid4().hex; _create_run(run_id,symbol,timeframe_scope,min_score,direction,lookback_days,params)
    try:
        store=HistoricalStore(store_root); cutoff=datetime.now(timezone.utc)-timedelta(days=int(lookback_days)); acquisition={}; errors={}
        needed=sorted(set(eval_tfs).union(REPLAY_CONTEXT),key=lambda x:("15m","1H","4H","D","5m").index(x) if x in REPLAY_CONTEXT else 99)
        for tf in needed:
            try: acquisition[tf]=acquire(symbol,tf,store_root=store_root,period=_period_for(tf,lookback_days)).to_dict()
            except Exception as exc: errors[f"acquire:{tf}"]=str(exc)
        frames={}
        for tf in needed:
            hist=store.load(symbol,tf)
            if len(hist): hist=hist.loc[hist.index>=cutoff]
            frames[tf]=hist
        all_events=[]; diagnostics={}
        for tf in eval_tfs:
            if len(frames.get(tf,[]))<=warmup_bars+1:
                diagnostics[tf]={"error":f"insufficient history ({len(frames.get(tf,[]))} rows)"}; continue
            events,diag=replay_timeframe(symbol,tf,frames,warmup_bars,forward_bars)
            events=[e for e in events if float(e.score)>=float(min_score) and (direction=="BOTH" or e.side==direction)]
            _persist_events(run_id,events); all_events.extend(events); diagnostics[tf]={**diag,"summary":summarize(events)}
        overall=summarize(all_events); overall.update({"run_id":run_id,"symbol":symbol,"scope":timeframe_scope,"minimum_score":float(min_score),"direction":direction,"lookback_days":int(lookback_days),"timeframes":diagnostics,"acquisition":acquisition,"errors":errors,"evidence_rows":len(all_events),"research_only":True,"policy_version":"V3.4E"})
        _finish_run(run_id,"COMPLETE",overall); return overall
    except Exception as exc:
        _finish_run(run_id,"FAILED",None,str(exc)); raise

def recent_experiments(limit:int=5):
    ensure_evidence_schema(); conn=get_connection(); cur=conn.cursor(); cur.execute("SELECT run_id,created_at,symbol,timeframe_scope,min_score,direction,lookback_days,status,summary_json FROM backtest_runs ORDER BY created_at DESC LIMIT %s",(int(limit),)); cols=["run_id","created_at","symbol","scope","min_score","direction","days","status","summary_json"]; out=[]
    for row in cur.fetchall():
        d=dict(zip(cols,row)); raw=d.pop("summary_json",None)
        try:d["summary"]=json.loads(raw) if raw else {}
        except Exception:d["summary"]={}
        out.append(d)
    cur.close(); conn.close(); return out

def evidence_stats():
    ensure_evidence_schema(); conn=get_connection(); cur=conn.cursor(); cur.execute("SELECT COUNT(*) FROM backtest_runs WHERE status='COMPLETE'"); runs=int(cur.fetchone()[0]); cur.execute("SELECT COUNT(*) FROM setup_observations"); obs=int(cur.fetchone()[0]); cur.execute("SELECT COUNT(*) FROM setup_observations WHERE outcome IN ('TARGET','STOP')"); resolved=int(cur.fetchone()[0]); cur.close(); conn.close(); return {"runs":runs,"observations":obs,"resolved":resolved}
