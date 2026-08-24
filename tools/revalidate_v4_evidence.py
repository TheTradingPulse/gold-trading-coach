from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
from v4_first_touch_contract import classify_first_touch


def wilson_low(k, n, z=1.96):
    if not n: return None
    p=k/n; d=1+z*z/n
    return (p+z*z/(2*n)-z*math.sqrt((p*(1-p)+z*z/(4*n))/n))/d


def safe_json(value):
    try: return json.loads(value or "{}")
    except Exception: return {}


def score_band(value):
    try: x=float(value)
    except Exception: return "UNKNOWN"
    if x > 10: x /= 10
    lo=math.floor(x*2)/2
    return f"{lo:.1f}-{lo+0.49:.2f}"


def summarize(groups):
    rows=[]
    for key, s in sorted(groups.items()):
        e=s["entered"]; p=s["primary_before_stop"]; q=s["stretch_before_stop"]
        rows.append({"group":key, **s,
            "primary_first_pct":round(100*p/e,3) if e else None,
            "primary_wilson_low_pct":round(100*wilson_low(p,e),3) if e else None,
            "stretch_first_pct":round(100*q/e,3) if e else None,
            "stretch_wilson_low_pct":round(100*wilson_low(q,e),3) if e else None})
    return rows


def audit_db(path):
    out={"path":str(path),"exists":path.exists(),"rows":0}
    groups={"symbol":defaultdict(lambda:defaultdict(int)),"score_band":defaultdict(lambda:defaultdict(int)),
            "symbol_score_band":defaultdict(lambda:defaultdict(int))}
    if not path.exists(): return out,groups
    con=sqlite3.connect(f"file:{path.as_posix()}?mode=ro",uri=True);con.row_factory=sqlite3.Row
    cols=[r[1] for r in con.execute("pragma table_info(observations)")]
    need=[c for c in ("symbol","score10","entered","primary_hit","stretch_hit","stop_hit","bars_to_entry",
          "bars_to_primary","bars_to_stretch","bars_to_outcome","same_bar_ambiguous","outcome_json") if c in cols]
    totals=defaultdict(int); classes=defaultdict(int)
    for row in con.execute("select "+",".join('"'+c+'"' for c in need)+" from observations"):
        r=dict(row);o=safe_json(r.get("outcome_json"));ft=classify_first_touch(r,o)
        out["rows"]+=1; totals["observations"]+=1
        if ft.entered: totals["entered"]+=1
        totals["primary_before_stop"]+=int(ft.primary_before_stop)
        totals["stretch_before_stop"]+=int(ft.stretch_before_stop)
        totals["same_bar_ambiguous"]+=int(ft.same_bar_ambiguous)
        totals["order_unknown"]+=int(ft.primary_class=="ORDER_UNKNOWN")
        classes[ft.primary_class]+=1
        sym=str(r.get("symbol") or "UNKNOWN").upper();band=score_band(r.get("score10"))
        for axis,key in (("symbol",sym),("score_band",band),("symbol_score_band",sym+"|"+band)):
            g=groups[axis][key];g["observations"]+=1;g["entered"]+=int(ft.entered)
            g["primary_before_stop"]+=int(ft.primary_before_stop);g["stretch_before_stop"]+=int(ft.stretch_before_stop)
            g["same_bar_ambiguous"]+=int(ft.same_bar_ambiguous);g["order_unknown"]+=int(ft.primary_class=="ORDER_UNKNOWN")
    con.close()
    e=totals["entered"]
    out["totals"]=dict(totals);out["primary_classes"]=dict(classes)
    out["verified_primary_first_pct"]=round(100*totals["primary_before_stop"]/e,4) if e else None
    out["verified_primary_wilson_low_pct"]=round(100*wilson_low(totals["primary_before_stop"],e),4) if e else None
    out["verified_stretch_first_pct"]=round(100*totals["stretch_before_stop"]/e,4) if e else None
    out["verified_stretch_wilson_low_pct"]=round(100*wilson_low(totals["stretch_before_stop"],e),4) if e else None
    return out,groups


def main():
    ap=argparse.ArgumentParser(description="Read-only first-touch revalidation of V4 evidence")
    ap.add_argument("--root",default=".");ap.add_argument("--out",default=None)
    a=ap.parse_args();root=Path(a.root).resolve();stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
    out=Path(a.out).resolve() if a.out else root/"research_data/v4/audits"/f"first_touch_revalidation_{stamp}"
    out.mkdir(parents=True,exist_ok=True)
    report={"version":"V4_FIRST_TOUCH_REVALIDATION_1","generated_utc":datetime.now(timezone.utc).isoformat(),
            "policy":"same-bar target/stop is ambiguous and never counted as target-first","databases":[]}
    all_rows=[]
    for p in (root/"research_data/v4/context_evidence_v4.db",root/"research_data/v4/evidence_v3.db"):
        info,groups=audit_db(p);report["databases"].append(info)
        for axis,g in groups.items():
            rows=summarize(g);all_rows.extend([{"database":p.name,"axis":axis,**r} for r in rows])
    (out/"first_touch_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    if all_rows:
        keys=["database","axis","group","observations","entered","primary_before_stop","primary_first_pct",
              "primary_wilson_low_pct","stretch_before_stop","stretch_first_pct","stretch_wilson_low_pct",
              "same_bar_ambiguous","order_unknown"]
        with (out/"first_touch_groups.csv").open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(all_rows)
    lines=["Trading Pulse First-Touch Revalidation",""]
    for d in report["databases"]:
        lines += [Path(d["path"]).name,
          f"  Rows: {d.get('rows',0)}",
          f"  Verified 3R-first: {d.get('verified_primary_first_pct')}%",
          f"  3R Wilson lower bound: {d.get('verified_primary_wilson_low_pct')}%",
          f"  Same-bar ambiguous: {(d.get('totals') or {}).get('same_bar_ambiguous',0)}",
          f"  Order unknown: {(d.get('totals') or {}).get('order_unknown',0)}",""]
    (out/"SUMMARY.txt").write_text("\n".join(lines),encoding="utf-8")
    zpath=out.with_suffix(".zip")
    with zipfile.ZipFile(zpath,"w",zipfile.ZIP_DEFLATED) as z:
        for p in out.iterdir():z.write(p,p.name)
    print("\n".join(lines));print(f"ZIP READY: {zpath}")


if __name__=="__main__": main()
