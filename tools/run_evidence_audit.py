from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import statistics
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


TICKS = {"GC": 0.10, "SI": 0.005, "ES": 0.25, "NQ": 0.25,
         "YM": 1.0, "RTY": 0.10, "CL": 0.01, "NG": 0.001}
MIN_NOISE_TICKS = 4


def pct(n, d):
    return round(100.0 * n / d, 4) if d else None


def wilson_low(k, n, z=1.96):
    if not n:
        return None
    p = k / n
    den = 1 + z * z / n
    return (p + z*z/(2*n) - z*math.sqrt((p*(1-p)+z*z/(4*n))/n)) / den


def qident(name):
    return '"' + str(name).replace('"', '""') + '"'


def first_table(con):
    names = [r[0] for r in con.execute(
        "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
    if "observations" in names:
        return "observations"
    return names[0] if names else None


def safe_json(value):
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}


def percentile(values, p):
    if not values:
        return None
    x = sorted(values)
    k = (len(x)-1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return round(x[lo] if lo == hi else x[lo]*(hi-k) + x[hi]*(k-lo), 6)


def audit_db(path: Path, detail_rows):
    result = {"path": str(path), "exists": path.exists(), "size_bytes": path.stat().st_size if path.exists() else 0}
    by_symbol = defaultdict(lambda: defaultdict(int))
    suspicious = []
    if not path.exists():
        return result, by_symbol, suspicious
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    table = first_table(con)
    if not table:
        result["error"] = "No user table found"
        con.close()
        return result, by_symbol, suspicious
    cols = [r[1] for r in con.execute(f"pragma table_info({qident(table)})")]
    result.update({"table": table, "columns": cols})
    total = con.execute(f"select count(*) from {qident(table)}").fetchone()[0]
    result["rows"] = total
    if "as_of" in cols:
        result["date_range"] = dict(zip(("min", "max"), con.execute(
            f"select min(as_of),max(as_of) from {qident(table)}").fetchone()))

    flags = [c for c in ("entered", "primary_hit", "stretch_hit", "stop_hit", "same_bar_ambiguous") if c in cols]
    if flags:
        sums = con.execute("select " + ",".join(f"sum(coalesce({qident(c)},0))" for c in flags) +
                           f" from {qident(table)}").fetchone()
        result["flag_totals"] = {c: int(v or 0) for c, v in zip(flags, sums)}
    if all(c in cols for c in ("entered", "primary_hit", "stop_hit")):
        entered, primary, stretch, stop, overlap3, overlap5 = con.execute(
            f"select sum(entered),sum(primary_hit),sum(coalesce(stretch_hit,0)),sum(stop_hit),"
            "sum(case when primary_hit=1 and stop_hit=1 then 1 else 0 end),"
            "sum(case when coalesce(stretch_hit,0)=1 and stop_hit=1 then 1 else 0 end) "
            f"from {qident(table)}").fetchone()
        result["outcomes"] = {
            "entered": int(entered or 0), "primary_hits": int(primary or 0),
            "stretch_hits": int(stretch or 0), "stop_hits": int(stop or 0),
            "primary_and_stop_overlap": int(overlap3 or 0),
            "stretch_and_stop_overlap": int(overlap5 or 0),
            "primary_hit_pct": pct(primary or 0, entered or 0),
            "stretch_hit_pct": pct(stretch or 0, entered or 0),
            "stop_hit_pct": pct(stop or 0, entered or 0),
            "wilson_3r_low_pct": round(100*wilson_low(primary or 0, entered or 0), 4) if entered else None,
            "mutually_exclusive": not bool(overlap3 or overlap5),
        }

    selected = [c for c in ("id", "symbol", "as_of", "setup_type", "direction", "score10", "entry", "stop",
                              "risk_points", "projected_rr", "entered", "primary_hit", "stretch_hit", "stop_hit",
                              "same_bar_ambiguous", "candidate_json", "outcome_json") if c in cols]
    score_values, risk_ticks_all = [], []
    for row in con.execute(f"select {','.join(map(qident, selected))} from {qident(table)}"):
        r = dict(row)
        sym = str(r.get("symbol") or "UNKNOWN").upper()
        agg = by_symbol[sym]
        agg["observations"] += 1
        for c in ("entered", "primary_hit", "stretch_hit", "stop_hit", "same_bar_ambiguous"):
            agg[c] += int(r.get(c) or 0)
        cand, out = safe_json(r.get("candidate_json")), safe_json(r.get("outcome_json"))
        score = r.get("score10", cand.get("setup_score"))
        try:
            score = float(score)
            if score > 10: score /= 10
            score_values.append(score)
        except Exception:
            score = None
        entry = r.get("entry", cand.get("projected_entry"))
        stop = r.get("stop", cand.get("projected_stop"))
        risk = r.get("risk_points", out.get("risk_points"))
        try:
            risk = abs(float(risk)) if risk is not None else abs(float(entry)-float(stop))
        except Exception:
            risk = None
        tick = TICKS.get(sym)
        risk_ticks = risk/tick if risk is not None and tick else None
        if risk_ticks is not None:
            risk_ticks_all.append(risk_ticks)
            agg["risk_available"] += 1
            if risk_ticks < MIN_NOISE_TICKS:
                agg["risk_under_4_ticks"] += 1
        if int(r.get("primary_hit") or 0) and int(r.get("stop_hit") or 0):
            agg["primary_and_stop_overlap"] += 1
            if len(suspicious) < detail_rows:
                suspicious.append({k: r.get(k) for k in selected if not k.endswith("_json")} |
                                  {"risk_ticks": round(risk_ticks, 3) if risk_ticks is not None else None,
                                   "issue": "primary_hit_and_stop_hit"})
    result["score10_distribution"] = {"n": len(score_values), "min": percentile(score_values, 0),
        "p25": percentile(score_values, .25), "median": percentile(score_values, .5),
        "p75": percentile(score_values, .75), "p95": percentile(score_values, .95), "max": percentile(score_values, 1)}
    result["risk_ticks_distribution"] = {"n": len(risk_ticks_all), "min": percentile(risk_ticks_all, 0),
        "p25": percentile(risk_ticks_all, .25), "median": percentile(risk_ticks_all, .5),
        "p75": percentile(risk_ticks_all, .75), "p95": percentile(risk_ticks_all, .95), "max": percentile(risk_ticks_all, 1),
        "under_4_ticks": sum(v["risk_under_4_ticks"] for v in by_symbol.values())}
    con.close()
    return result, by_symbol, suspicious


def audit_temporal(root: Path):
    base = root / "research_data" / "v4" / "temporal_regime_sniper"
    rules_path, report_path = base / "frozen_temporal_rules.json", base / "temporal_regime_report.json"
    out = {"rules_path": str(rules_path), "report_path": str(report_path),
           "rules_exists": rules_path.exists(), "report_exists": report_path.exists()}
    if not (rules_path.exists() and report_path.exists()): return out
    rules, report = json.loads(rules_path.read_text(encoding="utf-8")), json.loads(report_path.read_text(encoding="utf-8"))
    elite = rules.get("elite") or []
    out["elite_rule_count"] = len(elite)
    out["promotion"] = report.get("promotion")
    out["final_holdout"] = (report.get("final_holdout") or {}).get("elite")
    errors = []
    for i, rule in enumerate(elite):
        for source in ("stats", "calibration"):
            s = rule.get(source) or {}
            n, h = int(s.get("triggered") or 0), int(s.get("hit3") or 0)
            expected = round(wilson_low(h, n), 4) if n else None
            if expected != s.get("w3"):
                errors.append({"rule": i, "source": source, "reported_w3": s.get("w3"), "recomputed_w3": expected})
    out["wilson_recalculation_errors"] = errors
    out["dashboard_confidence_source"] = "per-rule calibration.w3 (95% Wilson lower bound for primary/3R hit)"
    out["holdout_w3_score10"] = round(10*float((out["final_holdout"] or {}).get("w3") or 0), 4)
    return out


def main():
    ap = argparse.ArgumentParser(description="Read-only Trading Pulse evidence and score audit")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default=None)
    ap.add_argument("--detail-rows", type=int, default=5000)
    args = ap.parse_args()
    root = Path(args.root).resolve()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(args.out).resolve() if args.out else root / "research_data" / "v4" / "audits" / f"score_evidence_audit_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    dbs = [root/"research_data"/"v4"/"context_evidence_v4.db", root/"research_data"/"v4"/"evidence_v3.db"]
    report = {"audit_version": "1.0-read-only", "generated_utc": datetime.now(timezone.utc).isoformat(),
              "root": str(root), "minimum_noise_ticks_test": MIN_NOISE_TICKS, "databases": [],
              "temporal_rules": audit_temporal(root)}
    all_symbols, all_suspicious = defaultdict(lambda: defaultdict(int)), []
    for db in dbs:
        info, symbols, suspicious = audit_db(db, args.detail_rows)
        report["databases"].append(info)
        for sym, values in symbols.items():
            for k, v in values.items(): all_symbols[sym][k] += v
        all_suspicious.extend([{"database": db.name, **x} for x in suspicious])
    report["combined_by_symbol"] = {s: dict(v) for s, v in sorted(all_symbols.items())}
    report["verdict_flags"] = {
        "outcomes_mutually_exclusive": all(d.get("outcomes", {}).get("mutually_exclusive", True) for d in report["databases"]),
        "first_touch_timestamps_present": any(any(c in d.get("columns", []) for c in
            ("entry_time", "stop_time", "primary_time", "stretch_time", "first_touch_time")) for d in report["databases"]),
        "structure_score_has_execution_noise_gate": False,
        "dashboard_confidence_uses_final_holdout": False,
    }
    (out/"audit_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    keys = sorted({k for v in all_symbols.values() for k in v})
    with (out/"by_symbol.csv").open("w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=["symbol"]+keys);w.writeheader()
        for sym, vals in sorted(all_symbols.items()): w.writerow({"symbol":sym, **vals})
    if all_suspicious:
        keys = sorted({k for r in all_suspicious for k in r})
        with (out/"overlap_examples.csv").open("w", newline="", encoding="utf-8") as f:
            w=csv.DictWriter(f, fieldnames=keys);w.writeheader();w.writerows(all_suspicious)
    summary = ["Trading Pulse Score & Evidence Audit", "", f"Output: {out}",
               f"Rows audited: {sum(d.get('rows',0) for d in report['databases'])}",
               f"Outcome flags mutually exclusive: {report['verdict_flags']['outcomes_mutually_exclusive']}",
               f"First-touch timestamps present: {report['verdict_flags']['first_touch_timestamps_present']}",
               f"Dashboard confidence uses final holdout: {report['verdict_flags']['dashboard_confidence_uses_final_holdout']}",
               f"Final-holdout Wilson score /10: {report['temporal_rules'].get('holdout_w3_score10')}"]
    (out/"SUMMARY.txt").write_text("\n".join(summary)+"\n", encoding="utf-8")
    zip_path = out.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in out.iterdir(): z.write(p, p.name)
    print("\n".join(summary))
    print(f"ZIP READY: {zip_path}")


if __name__ == "__main__":
    main()
