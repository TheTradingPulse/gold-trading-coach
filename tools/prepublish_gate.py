"""Fail-closed Git and release-safety gate for Trading Pulse."""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_TRACKED_PARTS = {
    ".env", ".venv", "research_data", "backups", "backup", "archive",
    "archives", "__pycache__", "node_modules",
}
FORBIDDEN_SUFFIXES = {
    ".db", ".sqlite", ".sqlite3", ".parquet", ".feather", ".arrow",
    ".dbn", ".zip", ".download", ".7z", ".p12", ".pfx", ".pem",
}
SECRET_PATTERNS = {
    "massive_or_polygon_key": re.compile(r"\bpl\d+_[A-Za-z0-9_-]{20,}\b"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "github_token": re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
    "telegram_token": re.compile(r"\b\d{7,12}:[A-Za-z0-9_-]{25,}\b"),
    "credential_url": re.compile(r"(?:postgres(?:ql)?|mysql)://[^\s:@/]+:[^\s@/]+@", re.I),
    "quoted_secret_assignment": re.compile(
        r"(?im)^\s*(?:set\s+|\$env:)?[A-Z0-9_]*(?:PASSWORD|TOKEN|API_KEY|SECRET)[A-Z0-9_]*"
        r"\s*=\s*['\"](?!YOUR_|CHANGE_ME|PLACEHOLDER|EXAMPLE)([^'\"]{8,})['\"]"
    ),
    "batch_secret_assignment": re.compile(
        r"(?im)^\s*set\s+[A-Z0-9_]*(?:PASSWORD|TOKEN|API_KEY|SECRET)[A-Z0-9_]*"
        r"\s*=\s*(?!%|YOUR_|CHANGE_ME|PLACEHOLDER|EXAMPLE)([^\r\n]{8,})$"
    ),
}
TEXT_SUFFIXES = {
    ".py", ".ps1", ".bat", ".cmd", ".json", ".toml", ".yaml", ".yml",
    ".ini", ".cfg", ".md", ".txt", ".sql", ".html", ".css", ".js", ".ts",
}


def git(*args: str) -> list[str]:
    completed = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "git command failed")
    return [line for line in completed.stdout.splitlines() if line.strip()]


def tracked_files() -> list[Path]:
    # Review the exact candidate set that `git add -A` would see: files already
    # tracked plus untracked files not excluded by the current .gitignore.
    return [
        ROOT / line
        for line in git("ls-files", "--cached", "--others", "--exclude-standard")
    ]


def forbidden_path(path: Path) -> str | None:
    relative = path.relative_to(ROOT)
    lowered = {part.lower() for part in relative.parts}
    hit = sorted(lowered.intersection(FORBIDDEN_TRACKED_PARTS))
    if hit:
        return f"forbidden tracked directory: {hit[0]}"
    if path.suffix.lower() in FORBIDDEN_SUFFIXES:
        return f"forbidden tracked suffix: {path.suffix.lower()}"
    return None


def secret_hits(path: Path) -> list[str]:
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {
        ".gitignore", ".env.example", "Procfile",
    }:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    return [name for name, pattern in SECRET_PATTERNS.items() if pattern.search(text)]


def syntax_errors(paths: list[Path]) -> list[str]:
    errors = []
    for path in paths:
        if path.suffix.lower() != ".py" or not path.exists():
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        except (SyntaxError, OSError) as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
    return errors


def main() -> int:
    checks = []
    failures = []
    tracked = tracked_files()

    forbidden = []
    secrets = []
    for path in tracked:
        reason = forbidden_path(path)
        if reason:
            forbidden.append(f"{path.relative_to(ROOT)} ({reason})")
        if path.exists():
            for kind in secret_hits(path):
                secrets.append(f"{path.relative_to(ROOT)} ({kind})")

    syntax = syntax_errors(tracked)
    registry_path = ROOT / "config" / "tradingpulse_registry.json"
    registry_ok = False
    registry_error = None
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8-sig"))
        registry_ok = registry.get("schema") == "TP_CANONICAL_SYSTEM_REGISTRY_1"
        if not registry_ok:
            registry_error = "unexpected registry schema"
    except Exception as exc:
        registry_error = str(exc)

    required = [
        ROOT / "dashboard.py",
        ROOT / "core" / "live_grading_service.py",
        ROOT / "core" / "canonical_contracts.py",
        ROOT / "core" / "execution_lifecycle_engine.py",
        ROOT / "core" / "account_risk_engine.py",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]

    checks.extend([
        {"name": "forbidden_tracked_files", "ok": not forbidden, "detail": forbidden},
        {"name": "credential_patterns", "ok": not secrets, "detail": secrets},
        {"name": "tracked_python_syntax", "ok": not syntax, "detail": syntax},
        {"name": "canonical_registry", "ok": registry_ok, "detail": registry_error},
        {"name": "required_release_files", "ok": not missing, "detail": missing},
    ])
    for check in checks:
        if not check["ok"]:
            failures.append(check["name"])

    report = {
        "schema": "TP_PREPUBLISH_GATE_1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_files": len(tracked),
        "passed": len(checks) - len(failures),
        "total": len(checks),
        "ready": not failures,
        "checks": checks,
    }
    output = ROOT / "prepublish_gate_report.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Trading Pulse Pre-Publish Gate")
    for check in checks:
        print(f"{'PASS' if check['ok'] else 'FAIL'}: {check['name']}")
        if not check["ok"]:
            for detail in check["detail"] if isinstance(check["detail"], list) else [check["detail"]]:
                print(f"  - {detail}")
    print(f"READY FOR COMMIT: {not failures}")
    print(f"REPORT: {output}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
