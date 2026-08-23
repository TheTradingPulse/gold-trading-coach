from __future__ import annotations
import sqlite3, json
from pathlib import Path
from datetime import datetime, timezone

class EvidenceStore:
    def __init__(self,path="research_data/v4/evidence.db"):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True); self._init()
    def _con(self): return sqlite3.connect(self.path,timeout=30)
    def _init(self):
        with self._con() as c:
            c.executescript("""CREATE TABLE IF NOT EXISTS observations(
            id INTEGER PRIMARY KEY AUTOINCREMENT, observed_at TEXT NOT NULL, symbol TEXT NOT NULL,
            timeframe TEXT, setup_id TEXT, setup_type TEXT, direction TEXT, score REAL,
            as_of TEXT NOT NULL, entry REAL, stop REAL, t1 REAL, t2 REAL, t3 REAL,
            outcome TEXT, mfe REAL, mae REAL, realized_r REAL, bars_to_entry INTEGER,
            bars_to_outcome INTEGER, context_json TEXT, engine_version TEXT);
            CREATE INDEX IF NOT EXISTS idx_obs_lookup ON observations(symbol,setup_type,score,as_of);
            """)
    def add(self,**row):
        allowed={"symbol","timeframe","setup_id","setup_type","direction","score","as_of","entry","stop",
                 "t1","t2","t3","outcome","mfe","mae","realized_r","bars_to_entry","bars_to_outcome",
                 "context_json","engine_version"}
        data={k:row.get(k) for k in allowed}
        data["observed_at"]=datetime.now(timezone.utc).isoformat()
        cols=list(data); vals=[data[k] for k in cols]
        with self._con() as c:
            c.execute(f"INSERT INTO observations({','.join(cols)}) VALUES({','.join('?' for _ in cols)})",vals)
    def summary(self,symbol=None,min_score=None):
        where=[]; args=[]
        if symbol: where.append("symbol=?"); args.append(symbol.upper())
        if min_score is not None: where.append("score>=?"); args.append(float(min_score))
        w=(" WHERE "+" AND ".join(where)) if where else ""
        with self._con() as c:
            r=c.execute(f"""SELECT COUNT(*),AVG(CASE WHEN realized_r IS NOT NULL THEN realized_r END),
            AVG(CASE WHEN outcome LIKE 'T1%' OR outcome LIKE 'T2%' OR outcome LIKE 'T3%' THEN 1.0 ELSE 0.0 END),
            AVG(mfe),AVG(mae) FROM observations{w}""",args).fetchone()
        return {"observations":r[0],"avg_r":r[1],"target_hit_rate":r[2],"avg_mfe":r[3],"avg_mae":r[4]}
