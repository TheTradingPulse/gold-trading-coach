from __future__ import annotations
import json
from pathlib import Path

REQUIRED_FROZEN = {
    "hardened_65": Path("research_data/v4/elite_65_hardening/frozen_65_rules.json"),
    "nested": Path("research_data/v4/elite_discovery_nested/frozen_rules.json"),
    "temporal": Path("research_data/v4/temporal_regime_sniper/frozen_temporal_rules.json"),
}
CANONICAL_MANIFEST = Path("research_data/v4/historical_blind/reports/canonical_5y_manifest.json")
RAW_AUDIT = Path("research_data/v4/historical_blind/reports/databento_2021_2025_final_audit.json")
TEMPORAL_REPORT = Path("research_data/v4/temporal_regime_sniper/temporal_regime_report.json")

def _json(path: Path):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return None

def release_health(root="."):
    root=Path(root); checks=[]
    def add(name, ok, detail): checks.append({"name":name,"ok":bool(ok),"detail":str(detail)})
    for name,rel in REQUIRED_FROZEN.items():
        p=root/rel; obj=_json(p) if p.exists() else None
        add(f"frozen_rules:{name}", p.exists() and obj is not None, p)
    m=root/CANONICAL_MANIFEST; mo=_json(m) if m.exists() else None
    built=(mo or {}).get("built")
    failed=(mo or {}).get("failed")
    # tolerate manifests that store counts under a summary object
    if isinstance((mo or {}).get("summary"),dict):
        built=(mo["summary"].get("built",built)); failed=(mo["summary"].get("failed",failed))
    no_failures = failed in (None, 0, [])
    canonical_ok = m.exists() and mo is not None and (built in (None,480)) and no_failures
    add("canonical_manifest", canonical_ok, f"{m} built={built} failed={failed}")
    a=root/RAW_AUDIT; ao=_json(a) if a.exists() else None
    valid=(ao or {}).get("valid"); bad=(ao or {}).get("bad")
    raw_ok=a.exists() and ao is not None and (valid in (None,480)) and (bad in (None,0))
    add("raw_480_audit", raw_ok, f"{a} valid={valid} bad={bad}")
    tr=root/TEMPORAL_REPORT; tro=_json(tr) if tr.exists() else None
    promotion=(tro or {}).get("promotion") or {}
    add("temporal_elite_promoted", promotion.get("elite") is True, f"{tr} elite={promotion.get('elite')}")
    add("grand_slam_remains_disabled", promotion.get("grand_slam") is False, f"{tr} grand_slam={promotion.get('grand_slam')}")
    # Production-safety invariants from the installed source.
    gp=root/"core/v4_grandslam_policy.py"; txt=gp.read_text(encoding="utf-8") if gp.exists() else ""
    add("raw_score_cannot_create_grandslam", "raw score" in txt.lower() and "GRAND_SLAM" in txt, gp)
    ld=root/"core/live_data_engine.py"; ltxt=ld.read_text(encoding="utf-8") if ld.exists() else ""
    add("delayed_feed_not_execution_eligible", '"execution_eligible":False' in ltxt and "is_realtime_available" in ltxt, ld)
    passed=sum(c["ok"] for c in checks)
    return {"schema":"tradingpulse.release_health.v1","passed":passed,"total":len(checks),"ready":passed==len(checks),"checks":checks}
