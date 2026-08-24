from __future__ import annotations
import hashlib,json,sqlite3
from pathlib import Path
SCHEMA_VERSION="4.0-context-evidence-v4"

def ensure(path="research_data/v4/context_evidence_v4.db"):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(p) as d:
        d.execute('''CREATE TABLE IF NOT EXISTS observations(
          id INTEGER PRIMARY KEY,evidence_key TEXT UNIQUE,symbol TEXT,replay_timeframe TEXT,as_of TEXT,
          setup_id TEXT,setup_type TEXT,direction TEXT,score10 REAL,grade TEXT,lifecycle TEXT,
          entered INTEGER,primary_hit INTEGER,stretch_hit INTEGER,stop_hit INTEGER,realized_r REAL,
          mfe_r REAL,mae_r REAL,bars_to_entry INTEGER,bars_to_outcome INTEGER,
          context_json TEXT,candidate_json TEXT,market_state_json TEXT,outcome_json TEXT,
          provider TEXT,engine_version TEXT)''')
        d.execute('CREATE INDEX IF NOT EXISTS ctx_identity ON observations(symbol,setup_type,direction,as_of)')
        d.execute('CREATE INDEX IF NOT EXISTS ctx_score ON observations(symbol,score10)')
    return p

def write(path,record,outcome,context,provider="yahoo"):
    c=record.get("candidate_payload",{});score=c.get("setup_score",c.get("quality_score",c.get("score")))
    try: score=float(score); score=score/10.0 if score>10 else score
    except: score=None
    raw='|'.join(map(str,[record.get("symbol"),record.get("as_of"),record.get("setup_id"),record.get("entry"),record.get("stop")]))
    key=hashlib.sha256(raw.encode()).hexdigest()
    vals=(key,record.get("symbol"),record.get("replay_timeframe"),record.get("as_of"),record.get("setup_id"),
      record.get("setup_type"),record.get("direction"),score,record.get("grade"),record.get("lifecycle"),
      int(bool(outcome.get("entered"))),int(bool(outcome.get("primary_hit"))),int(bool(outcome.get("stretch_hit"))),
      int(bool(outcome.get("stop_hit"))),outcome.get("realized_r"),outcome.get("mfe_r"),outcome.get("mae_r"),
      outcome.get("bars_to_entry"),outcome.get("bars_to_outcome"),json.dumps(context,default=str),
      json.dumps(c,default=str),json.dumps(record.get("market_state",{}),default=str),json.dumps(outcome,default=str),provider,SCHEMA_VERSION)
    with sqlite3.connect(ensure(path)) as d:
        q='INSERT OR IGNORE INTO observations VALUES(NULL,'+','.join(['?']*len(vals))+')'
        cur=d.execute(q,vals);d.commit();return cur.rowcount==1

def load(path="research_data/v4/context_evidence_v4.db"):
    with sqlite3.connect(ensure(path)) as d:
        d.row_factory=sqlite3.Row
        rows=[]
        for x in d.execute('SELECT * FROM observations ORDER BY as_of,id'):
            r=dict(x)
            try:r['_features']=json.loads(r.pop('context_json') or '{}')
            except:r['_features']={}
            rows.append(r)
        return rows
