from __future__ import annotations

import ast
import csv
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"C:\TradingPulse")
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = ROOT / "research_data" / "system_audits" / f"whole_system_{STAMP}"
SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache", ".mypy_cache"}
CODE_EXT = {".py", ".ps1", ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".md", ".txt", ".sql"}
HASH_MAX = 25 * 1024 * 1024


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rel(path: Path) -> str:
    try: return str(path.relative_to(ROOT))
    except Exception: return str(path)


def walk_files():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        bp = Path(base)
        # Raw market history was already validated by dedicated data audits.
        # Do not descend into it during the architecture inventory.
        normalized = str(bp).replace("/", "\\").lower()
        if "research_data\\v4\\historical_blind\\raw" in normalized:
            dirs[:] = []
            continue
        for name in files:
            p = bp / name
            try:
                st = p.stat()
                yield p, st
            except OSError:
                continue


def inventory():
    rows=[]; hashes=defaultdict(list); names=defaultdict(list)
    for p,st in walk_files():
        rp=rel(p); ext=p.suffix.lower()
        category = "raw_market_data" if "historical_blind\\raw" in rp.lower() else (
            "database" if ext in {".db",".sqlite",".sqlite3"} else "code_config" if ext in CODE_EXT else "other")
        digest=""
        if st.st_size <= HASH_MAX and category != "raw_market_data":
            try: digest=sha(p); hashes[digest].append(rp)
            except OSError: pass
        rows.append({"path":rp,"size_bytes":st.st_size,"mtime_utc":datetime.fromtimestamp(st.st_mtime,timezone.utc).isoformat(),
                     "extension":ext,"category":category,"sha256":digest})
        names[p.name.lower()].append(rp)
    dup_hash=[{"sha256":h,"copies":len(v),"paths":v} for h,v in hashes.items() if len(v)>1]
    dup_name=[{"name":n,"copies":len(v),"paths":v} for n,v in names.items() if len(v)>1]
    return rows,dup_hash,dup_name


def python_audit(file_rows):
    modules=[]; failures=[]; edges=[]; definitions=[]
    py_paths=[ROOT/r["path"] for r in file_rows if r["extension"]==".py" and r["category"]!="raw_market_data"]
    for p in py_paths:
        try:
            text=p.read_text(encoding="utf-8",errors="replace")
            tree=ast.parse(text,filename=str(p))
            imports=[]
            for node in ast.walk(tree):
                if isinstance(node,ast.Import): imports += [a.name for a in node.names]
                elif isinstance(node,ast.ImportFrom): imports.append(node.module or "")
                elif isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                    definitions.append({"file":rel(p),"type":type(node).__name__,"name":node.name,"line":node.lineno})
            for i in imports: edges.append({"file":rel(p),"import":i})
            modules.append({"file":rel(p),"lines":text.count("\n")+1,"imports":len(imports),"definitions":sum(1 for d in definitions if d["file"]==rel(p))})
        except SyntaxError as e:
            failures.append({"file":rel(p),"line":e.lineno,"error":e.msg})
        except Exception as e:
            failures.append({"file":rel(p),"error":repr(e)})
    return modules,failures,edges,definitions


def db_audit(file_rows):
    out=[]
    for r in file_rows:
        if r["category"]!="database": continue
        p=ROOT/r["path"]; item={"path":r["path"],"size_bytes":r["size_bytes"],"tables":[]}
        try:
            con=sqlite3.connect(f"file:{p.as_posix()}?mode=ro",uri=True,timeout=5)
            # Schema-only connection. Multi-GB integrity and row scans belong to
            # the dedicated evidence audits and can take hours on Windows.
            item["quick_check"]="skipped_in_fast_architecture_audit"
            tables=[x[0] for x in con.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
            for t in tables:
                cols=[{"name":x[1],"type":x[2],"pk":bool(x[5])} for x in con.execute(f'pragma table_info("{t}")')]
                count=None
                item["tables"].append({"name":t,"columns":cols,"row_count":count})
            con.close()
        except Exception as e: item["error"]=repr(e)
        out.append(item)
    return out


def text_audit(file_rows):
    invalid_json=[]; env_keys=[]; references=[]; stale=[]; entrypoints=[]
    patterns=re.compile(r"(?:research_data|C:\\\\TradingPulse|\.db\b|\.json\b|streamlit|uvicorn|FastAPI)",re.I)
    for r in file_rows:
        p=ROOT/r["path"]; rp=r["path"]
        low=p.name.lower()
        if any(x in low for x in ["backup","before_","before-","old","copy","deprecated","legacy"]): stale.append(rp)
        if low in {"dashboard.py","app.py","main.py","server.py"} or low.startswith("run_") or p.suffix.lower()==".ps1": entrypoints.append(rp)
        if p.name.startswith(".env") and r["size_bytes"]<2_000_000:
            try:
                for line in p.read_text(encoding="utf-8",errors="ignore").splitlines():
                    if "=" in line and not line.lstrip().startswith("#"): env_keys.append({"file":rp,"key":line.split("=",1)[0].strip()})
            except OSError: pass
        if p.suffix.lower()==".json" and r["size_bytes"]<25_000_000:
            try: json.loads(p.read_text(encoding="utf-8",errors="strict"))
            except Exception as e: invalid_json.append({"file":rp,"error":str(e)})
        if p.suffix.lower() in {".py",".ps1",".json",".toml",".yaml",".yml",".ini",".cfg"} and r["size_bytes"]<5_000_000:
            try:
                for no,line in enumerate(p.read_text(encoding="utf-8",errors="ignore").splitlines(),1):
                    if patterns.search(line): references.append({"file":rp,"line":no,"text":line.strip()[:500]})
            except OSError: pass
    return invalid_json,env_keys,references,stale,entrypoints


def git_info():
    def run(args):
        try: return subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=20).stdout.strip()
        except Exception as e: return repr(e)
    return {"status":run(["git","status","--short","--branch"]),"branches":run(["git","branch","-vv"]),
            "recent_log":run(["git","log","-n","20","--date=iso","--pretty=format:%h|%ad|%s"])}


def write_csv(name,rows):
    if not rows: return
    keys=[]
    for r in rows:
        for k in r:
            if k not in keys: keys.append(k)
    with (OUT/name).open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    files,dup_hash,dup_name=inventory()
    modules,syntax,imports,definitions=python_audit(files)
    dbs=db_audit(files)
    invalid_json,env_keys,references,stale,entrypoints=text_audit(files)
    report={"schema":"TP_WHOLE_SYSTEM_AUDIT_1","generated_utc":datetime.now(timezone.utc).isoformat(),
            "root":str(ROOT),"read_only":True,"summary":{"files":len(files),"python_files":len(modules),
            "python_syntax_failures":len(syntax),"databases":len(dbs),"duplicate_hash_groups":len(dup_hash),
            "duplicate_name_groups":len(dup_name),"stale_named_candidates":len(stale),"entrypoints":len(entrypoints),
            "invalid_json":len(invalid_json)},"git":git_info(),"duplicate_hashes":dup_hash,"duplicate_names":dup_name,
            "databases":dbs,"syntax_failures":syntax,"invalid_json":invalid_json,"environment_key_names":env_keys,
            "stale_named_candidates":stale,"entrypoints":entrypoints}
    (OUT/"whole_system_audit.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    write_csv("file_inventory.csv",files);write_csv("python_modules.csv",modules);write_csv("python_imports.csv",imports)
    write_csv("python_definitions.csv",definitions);write_csv("data_and_runtime_references.csv",references)
    summary=["# Trading Pulse Whole-System Audit","",f"Generated: {report['generated_utc']}","",
             "## Summary",*(f"- {k}: {v}" for k,v in report["summary"].items()),"",
             "No deletion or cleanup has been performed. All stale and duplicate findings are candidates only."]
    (OUT/"AUDIT_SUMMARY.md").write_text("\n".join(summary),encoding="utf-8")
    result=Path.home()/"Downloads"/f"TradingPulse_Whole_System_Audit_Result_{STAMP}.zip"
    names=["whole_system_audit.json","AUDIT_SUMMARY.md","file_inventory.csv","python_modules.csv","python_imports.csv","python_definitions.csv","data_and_runtime_references.csv"]
    with zipfile.ZipFile(result,"w",zipfile.ZIP_DEFLATED) as z:
        for n in names:
            p=OUT/n
            if p.exists(): z.write(p,arcname=n)
    print("Trading Pulse Whole-System Audit")
    for k,v in report["summary"].items(): print(f"{k}: {v}")
    print(f"AUDIT FOLDER: {OUT}")
    print(f"RESULT ZIP READY: {result}")


if __name__=="__main__": main()
