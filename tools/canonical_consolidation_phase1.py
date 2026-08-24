from __future__ import annotations

import hashlib
import json
import os
import py_compile
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"C:\TradingPulse")
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
ARCHIVE = ROOT / "archive" / f"legacy_phase1_{STAMP}"
BACKUPS = ROOT / "backups"
MANIFEST = ARCHIVE / "archive_manifest.json"


def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()


def code_files():
    allowed={".py",".ps1",".json",".toml",".yaml",".yml",".ini",".cfg",".sql",".md",".txt"}
    blocked={".git",".venv",".venv-history","__pycache__","node_modules","research_data","archive","backups"}
    for base,dirs,files in os.walk(ROOT):
        dirs[:]=[d for d in dirs if d not in blocked]
        for name in files:
            p=Path(base)/name
            if p.suffix.lower() in allowed: yield p


def checkpoint() -> Path:
    BACKUPS.mkdir(parents=True,exist_ok=True)
    target=BACKUPS/f"TradingPulse_before_canonical_consolidation_{STAMP}.zip"
    with zipfile.ZipFile(target,"w",zipfile.ZIP_DEFLATED) as z:
        for p in code_files(): z.write(p,arcname=str(p.relative_to(ROOT)))
    return target


def candidates():
    items=[]
    old_env=ROOT/".venv-history"
    if old_env.exists(): items.append(old_env)
    patterns=[
        "dashboard.before*.py","dashboard_before*.py","dashboard_working_before*.py",
        "INSTALL_BACKTEST_WORKSPACE_V3*.ps1","INSTALL_DEVELOPING_*.ps1","INSTALL_PROFESSOR_WORKSPACE_*.ps1",
    ]
    for pat in patterns: items.extend(ROOT.glob(pat))
    for name in ["run.py","reset_data.py","reset_gc_data.py"]:
        p=ROOT/name
        if p.exists(): items.append(p)
    tool_names=["dashboard_reference_20260823.py","install_backtest_workspace_v3.py","install_backtest_workspace_v31.py",
                "install_developing_setups.py","install_developing_trade_brief.py","install_professor_workspace_v2.py",
                "move_trade_brief_to_command_v34.py","reorder_backtest_workspace_v33.py","restore_manual_backtest_lab.py"]
    for name in tool_names:
        p=ROOT/"tools"/name
        if p.exists(): items.append(p)
    unique=[];seen=set()
    for p in items:
        key=str(p.resolve()).lower()
        if key not in seen: seen.add(key);unique.append(p)
    return unique


def move_to_archive(items):
    ARCHIVE.mkdir(parents=True,exist_ok=True); records=[]
    for src in items:
        relative=src.relative_to(ROOT); dst=ARCHIVE/relative;dst.parent.mkdir(parents=True,exist_ok=True)
        file_records=[]
        if src.is_file(): file_records=[{"path":str(relative),"sha256":digest(src),"size":src.stat().st_size}]
        elif src.is_dir():
            # Directory moves on the same volume are recoverable and nearly
            # instantaneous. Do not hash thousands of environment files.
            file_records=[{"path":str(relative),"directory":True,"hashing":"skipped_for_speed"}]
        shutil.move(str(src),str(dst))
        records.append({"source":str(relative),"archive":str(dst.relative_to(ROOT)),"files":file_records})
    return records


def rollback_script(records):
    lines=["$ErrorActionPreference = 'Stop'","Set-Location C:\\TradingPulse",f"$archive = 'C:\\TradingPulse\\{ARCHIVE.relative_to(ROOT)}'",""]
    for r in reversed(records):
        src=(ROOT/r["source"]); arc=(ROOT/r["archive"])
        lines += [f"if (Test-Path -LiteralPath '{arc}') {{",f"    New-Item -ItemType Directory -Force -Path '{src.parent}' | Out-Null",
                  f"    Move-Item -LiteralPath '{arc}' -Destination '{src}' -Force","}"]
    lines += ["Write-Host 'PHASE 1 ARCHIVE RESTORED' -ForegroundColor Green"]
    (ARCHIVE/"ROLLBACK_PHASE1.ps1").write_text("\n".join(lines),encoding="utf-8")


def install_registry_files():
    # Package extraction already places these files. This verifies their presence.
    for p in [ROOT/"config"/"tradingpulse_registry.json",ROOT/"docs"/"CANONICAL_ARCHITECTURE.md",
              ROOT/"core"/"system_registry.py",ROOT/"tools"/"verify_canonical_system.py"]:
        if not p.exists(): raise FileNotFoundError(p)


def main():
    dashboard=ROOT/"dashboard.py"
    before=digest(dashboard)
    checkpoint_path=checkpoint()
    items=candidates();records=move_to_archive(items)
    rollback_script(records);install_registry_files()
    py_compile.compile(str(dashboard),doraise=True)
    py_compile.compile(str(ROOT/"core"/"system_registry.py"),doraise=True)
    after=digest(dashboard)
    if before!=after: raise RuntimeError("dashboard.py changed during consolidation")
    payload={"schema":"TP_CANONICAL_CONSOLIDATION_PHASE1_1","created_utc":datetime.now(timezone.utc).isoformat(),
             "checkpoint":str(checkpoint_path),"dashboard_sha256_before":before,"dashboard_sha256_after":after,
             "dashboard_unchanged":True,"archive":str(ARCHIVE),"moved":records,"permanent_deletions":0}
    MANIFEST.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    print("Trading Pulse Canonical Consolidation - Phase 1")
    print(f"Checkpoint: {checkpoint_path}")
    print(f"Archived items: {len(records)}")
    print(f"Archive: {ARCHIVE}")
    print("Permanent deletions: 0")
    print("Dashboard unchanged: True")
    print(f"Rollback: {ARCHIVE / 'ROLLBACK_PHASE1.ps1'}")
    print("Run next: .venv\\Scripts\\python.exe tools\\verify_canonical_system.py")


if __name__=="__main__": main()
