from __future__ import annotations
import json, sqlite3
from pathlib import Path
from v4_score_contract import score10, score100, tier, flags

SCHEMA_VERSION = "4.0-evidence-v3"

def ensure(path="research_data/v4/evidence_v3.db"):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(p) as d:
        d.execute("""CREATE TABLE IF NOT EXISTS observations(
            id INTEGER PRIMARY KEY,
            evidence_key TEXT UNIQUE,
            symbol TEXT,
            replay_timeframe TEXT,
            setup_timeframe TEXT,
            as_of TEXT,
            setup_id TEXT,
            setup_type TEXT,
            direction TEXT,
            score10 REAL,
            score100 REAL,
            grade TEXT,
            lifecycle TEXT,
            research_tier TEXT,
            is_actionable INTEGER,
            is_elite_structural INTEGER,
            entry REAL,
            stop REAL,
            risk_points REAL,
            primary_r REAL,
            stretch_r REAL,
            primary_target REAL,
            stretch_target REAL,
            projected_rr REAL,
            outcome TEXT,
            entered INTEGER,
            primary_hit INTEGER,
            stretch_hit INTEGER,
            stop_hit INTEGER,
            bars_to_entry INTEGER,
            bars_to_primary INTEGER,
            bars_to_stretch INTEGER,
            bars_to_outcome INTEGER,
            raw_mfe_points REAL,
            raw_mae_points REAL,
            raw_mfe_r REAL,
            raw_mae_r REAL,
            alive_mfe_points REAL,
            alive_mae_points REAL,
            alive_mfe_r REAL,
            alive_mae_r REAL,
            achieved_r REAL,
            realized_r REAL,
            same_bar_ambiguous INTEGER,
            candidate_json TEXT,
            market_state_json TEXT,
            outcome_json TEXT,
            provider TEXT,
            engine_version TEXT
        )""")
        d.execute("CREATE INDEX IF NOT EXISTS ev3_symbol ON observations(symbol,as_of)")
        d.execute("CREATE INDEX IF NOT EXISTS ev3_score ON observations(symbol,score10)")
        d.execute("CREATE INDEX IF NOT EXISTS ev3_tier ON observations(research_tier,score10)")
    return p

def write(path, record, outcome, provider="yahoo"):
    c = record["candidate_payload"]
    x = flags(c)
    elite = all(x[k] for k in (
        "score_9_0","active","timeframe_valid","zone_quality_75",
        "freshness_70","retests_le_1","rr_2"
    ))
    key = "|".join(map(str, [
        record["symbol"], record["as_of"], record["setup_id"],
        record.get("entry"), record.get("stop"),
        outcome.get("primary_target"), outcome.get("stretch_target")
    ]))
    vals = (
        key, record["symbol"], record.get("replay_timeframe"), record.get("timeframe"),
        record["as_of"], record["setup_id"], record.get("setup_type"), record.get("direction"),
        score10(c), score100(c), record.get("grade"), record.get("lifecycle"), tier(c),
        int(record.get("is_actionable",False)), int(elite),
        record.get("entry"), record.get("stop"), outcome.get("risk_points"),
        outcome.get("primary_r"), outcome.get("stretch_r"),
        outcome.get("primary_target"), outcome.get("stretch_target"),
        record.get("projected_rr"), outcome.get("outcome"), int(outcome.get("entered",False)),
        int(outcome.get("primary_hit",False)), int(outcome.get("stretch_hit",False)),
        int(outcome.get("stop_hit",False)), outcome.get("bars_to_entry"),
        outcome.get("bars_to_primary"), outcome.get("bars_to_stretch"), outcome.get("bars_to_outcome"),
        outcome.get("raw_mfe_points"), outcome.get("raw_mae_points"),
        outcome.get("raw_mfe_r"), outcome.get("raw_mae_r"),
        outcome.get("alive_mfe_points"), outcome.get("alive_mae_points"),
        outcome.get("alive_mfe_r"), outcome.get("alive_mae_r"),
        outcome.get("achieved_r"), outcome.get("realized_r"),
        int(outcome.get("same_bar_ambiguous",False)),
        json.dumps(c,default=str), json.dumps(record["market_state"],default=str),
        json.dumps(outcome,default=str), provider, SCHEMA_VERSION
    )
    with sqlite3.connect(ensure(path)) as d:
        q = "INSERT OR IGNORE INTO observations VALUES(NULL," + ",".join(["?"]*len(vals)) + ")"
        cur = d.execute(q, vals)
        d.commit()
        return cur.rowcount == 1
