from __future__ import annotations
import sqlite3, json, hashlib
from pathlib import Path
from datetime import datetime, timezone

class LearningStore:
    def __init__(self,path="research_data/v4/professor_learning.db"):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True); self._init()
    def _con(self): return sqlite3.connect(self.path,timeout=30)
    def _init(self):
        with self._con() as c:
            c.executescript("""CREATE TABLE IF NOT EXISTS qa(
            id INTEGER PRIMARY KEY AUTOINCREMENT, asked_at TEXT NOT NULL, symbol TEXT, question TEXT NOT NULL,
            answer TEXT, useful INTEGER, wrong INTEGER, grounding_json TEXT, model TEXT);
            CREATE TABLE IF NOT EXISTS claims(
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, claim_hash TEXT UNIQUE,
            claim TEXT NOT NULL, topic TEXT, source_json TEXT, evidence_json TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING', reviewed_at TEXT, reviewer_note TEXT);
            CREATE INDEX IF NOT EXISTS idx_claim_status ON claims(status,topic);""")
    def log_qa(self,question,answer=None,symbol=None,grounding=None,model=None):
        with self._con() as c:
            cur=c.execute("INSERT INTO qa(asked_at,symbol,question,answer,grounding_json,model) VALUES(?,?,?,?,?,?)",
              (datetime.now(timezone.utc).isoformat(),symbol,question,answer,json.dumps(grounding or {}),model))
            return cur.lastrowid
    def feedback(self,qa_id,useful=None,wrong=None):
        with self._con() as c:
            c.execute("UPDATE qa SET useful=COALESCE(?,useful),wrong=COALESCE(?,wrong) WHERE id=?",
                      (None if useful is None else int(bool(useful)),None if wrong is None else int(bool(wrong)),qa_id))
    def propose_claim(self,claim,topic=None,sources=None,evidence=None):
        h=hashlib.sha256(claim.strip().lower().encode()).hexdigest()
        with self._con() as c:
            c.execute("""INSERT OR IGNORE INTO claims(created_at,claim_hash,claim,topic,source_json,evidence_json,status)
                         VALUES(?,?,?,?,?,?, 'PENDING')""",
                      (datetime.now(timezone.utc).isoformat(),h,claim,topic,json.dumps(sources or []),json.dumps(evidence or {})))
        return h
    def review_claim(self,claim_hash,status,note=None):
        status=status.upper()
        if status not in {"VERIFIED","REJECTED","PENDING"}: raise ValueError("invalid review status")
        with self._con() as c:
            c.execute("UPDATE claims SET status=?,reviewed_at=?,reviewer_note=? WHERE claim_hash=?",
                      (status,datetime.now(timezone.utc).isoformat(),note,claim_hash))
    def metrics(self):
        with self._con() as c:
            q=c.execute("SELECT COUNT(*),SUM(COALESCE(useful,0)),SUM(COALESCE(wrong,0)) FROM qa").fetchone()
            claims=dict(c.execute("SELECT status,COUNT(*) FROM claims GROUP BY status").fetchall())
        return {"questions":q[0],"useful":q[1] or 0,"wrong":q[2] or 0,"claims":claims}
