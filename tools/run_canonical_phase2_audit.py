from __future__ import annotations

import csv
import json
import sqlite3
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(r"C:\TradingPulse")
sys.path.insert(0,str(ROOT/"core"))
from canonical_adapters import from_v6_row

DB=ROOT/"research_data"/"v6"/"professional_zone_reference.db"
OUT=ROOT/"research_data"/"canonical"/"phase2"
REQUIRED={"zone_id","symbol","pattern","direction","formed_at","entry_ts","entry","stop","risk","ota_score","max_verified_r","max_possible_r"}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(f"file:{DB.as_posix()}?mode=ro",uri=True)
    integrity=con.execute("pragma quick_check(1)").fetchone()[0]
    cols=[x[1] for x in con.execute('pragma table_info("professional_zones")')]
    missing=sorted(REQUIRED-set(cols))
    if missing: raise RuntimeError(f"V6 schema missing required fields: {missing}")
    cur=con.execute("select * from professional_zones"); names=[x[0] for x in cur.description]
    issues=Counter();symbols=Counter();patterns=Counter();rows=0;unique=set();dupes=0
    examples=[]
    for values in cur:
        row=dict(zip(names,values));rows+=1
        setup,outcome=from_v6_row(row)
        symbols[setup.symbol]+=1;patterns[setup.pattern]+=1
        if setup.setup_id in unique: dupes+=1
        unique.add(setup.setup_id)
        found=setup.validate()+outcome.validate()
        for issue in found: issues[issue]+=1
        if found and len(examples)<100: examples.append({"setup_id":setup.setup_id,"symbol":setup.symbol,"issues":"|".join(found)})
    con.close()
    compatibility={
      "live_detector":"SetupCandidate V3.1E demand/supply across multiple timeframes",
      "research_detector":"V6 5m RBR/DBR/RBD/DBD professional zones",
      "direct_policy_parity":False,
      "reason":"Detector definitions and scoring features differ; an evidence lookup may not match by raw score or pattern name.",
      "required_next":"Replay the live detector over the V5 warehouse OR promote V6 detector into production after snapshot parity tests."
    }
    report={"schema":"TP_CANONICAL_PHASE2_AUDIT_1","generated_utc":datetime.now(timezone.utc).isoformat(),
            "database":str(DB),"database_quick_check":integrity,"rows":rows,"unique_setup_ids":len(unique),
            "duplicate_setup_ids":dupes,"symbols":dict(symbols),"patterns":dict(patterns),"issues":dict(issues),
            "required_columns_missing":missing,"compatibility":compatibility,
            "decision":"FAIL_CLOSED_NO_LIVE_PROMOTION"}
    (OUT/"canonical_phase2_audit.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    with (OUT/"canonical_phase2_issue_examples.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["setup_id","symbol","issues"]);w.writeheader();w.writerows(examples)
    registry_path=ROOT/"config"/"tradingpulse_registry.json"
    registry=json.loads(registry_path.read_text(encoding="utf-8"));registry["status"]="CONSOLIDATION_PHASE_2_AUDITED"
    registry["contracts"].update({"canonical_setup":"core/canonical_contracts.py:CanonicalSetup",
                                  "canonical_outcome":"core/canonical_contracts.py:CanonicalOutcome",
                                  "evidence_decision":"core/canonical_contracts.py:EvidenceDecision"})
    registry_path.write_text(json.dumps(registry,indent=2),encoding="utf-8")
    result=Path.home()/"Downloads"/"TradingPulse_Canonical_Phase2_Result_20260823.zip"
    with zipfile.ZipFile(result,"w",zipfile.ZIP_DEFLATED) as z:
        z.write(OUT/"canonical_phase2_audit.json",arcname="canonical_phase2_audit.json")
        z.write(OUT/"canonical_phase2_issue_examples.csv",arcname="canonical_phase2_issue_examples.csv")
        z.write(registry_path,arcname="tradingpulse_registry.json")
    print("Trading Pulse Canonical Phase 2 Audit")
    print(f"Database integrity: {integrity}")
    print(f"V6 zones audited: {rows:,}")
    print(f"Duplicate setup IDs: {dupes}")
    print(f"Contract issue rows: {sum(issues.values()):,}")
    for k,v in issues.most_common(): print(f"  {k}: {v:,}")
    print("Live promotion: BLOCKED (intentional)")
    print(f"RESULT ZIP READY: {result}")


if __name__=="__main__": main()
