from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(r"C:\TradingPulse")
V6 = ROOT / "research_data" / "v6"
LAB = V6 / "massive_move_lab"
DB = V6 / "professional_zone_reference.db"
OUT = V6 / "massive_move_zone_link"
COST_R = 0.05


def wilson_lower(w: int, n: int, z: float = 1.96) -> float:
    if n <= 0: return float("nan")
    p = w/n; den = 1+z*z/n
    return (p+z*z/(2*n)-z*math.sqrt((p*(1-p)+z*z/(4*n))/n))/den


def period_from_date(x: pd.Series) -> np.ndarray:
    y = pd.to_datetime(x).dt.year
    return np.select([y <= 2023, y == 2024], ["development", "calibration"], default="holdout")


def read_zones() -> pd.DataFrame:
    if not DB.exists(): raise FileNotFoundError(DB)
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    integrity = con.execute("pragma integrity_check").fetchone()[0]
    if integrity != "ok": raise RuntimeError(f"Database integrity: {integrity}")
    z = pd.read_sql_query("select * from professional_zones", con)
    con.close()
    return z


def attach_sessions(z: pd.DataFrame, d: pd.DataFrame) -> pd.DataFrame:
    z = z.copy()
    z["entry_ts"] = pd.to_datetime(z.entry_ts, utc=True, errors="coerce")
    z = z.dropna(subset=["entry_ts", "symbol"])
    local = z.entry_ts.dt.tz_convert("America/New_York")
    z["session_date"] = (local + pd.Timedelta(hours=6)).dt.date.astype(str)
    z["entry_hour_et"] = local.dt.hour + local.dt.minute/60
    keep = ["symbol","session_date","massive","massive_score","prior_range_to_atr","gap_atr",
            "opening_range_atr","direction","period"]
    d = d[keep].rename(columns={"direction":"session_direction"})
    x = z.merge(d, on=["symbol","session_date"], how="left", validate="many_to_one")
    x["period"] = x.period.fillna(pd.Series(period_from_date(x.session_date), index=x.index))
    x["massive"] = x.massive.fillna(False).astype(bool)
    x["direction_aligned"] = x.direction.astype(str).str.upper().eq(x.session_direction.astype(str).str.upper())
    x["prior_expansion"] = x.prior_range_to_atr.ge(1.25)
    x["gap_large"] = x.gap_atr.ge(0.35)
    # Opening 90-minute range is only legitimate for entries at/after 11:00 ET.
    x["opening_drive_available"] = x.entry_hour_et.ge(11.0)
    x["opening_drive_large_at_entry"] = x.opening_drive_available & x.opening_range_atr.ge(0.55)
    return x


def ladder(x: pd.DataFrame, group_cols: list[str], label: str) -> pd.DataFrame:
    rows = []
    for keys, q in x.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple): keys = (keys,)
        base = dict(zip(group_cols, keys))
        verified = pd.to_numeric(q.max_verified_r, errors="coerce").fillna(-np.inf)
        possible = pd.to_numeric(q.max_possible_r, errors="coerce").fillna(verified)
        for rr in range(1, 21):
            wins = int((verified >= rr).sum())
            possible_wins = int((possible >= rr).sum())
            n = len(q); ambiguous = max(0, possible_wins-wins)
            rate = wins/n if n else np.nan
            wl = wilson_lower(wins,n)
            rows.append({"dimension":label, **base, "rr":rr, "n":n, "wins":wins,
                         "ambiguous":ambiguous, "verified_rate":rate,
                         "expectancy_after_cost":rate*rr-(1-rate)-COST_R,
                         "wilson_expectancy_after_cost":wl*rr-(1-wl)-COST_R})
    return pd.DataFrame(rows)


def feature_enrichment(x: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    features={
        "prior_expansion":x.prior_expansion,
        "gap_large":x.gap_large,
        "opening_drive_large_at_entry":x.opening_drive_large_at_entry,
        "direction_aligned":x.direction_aligned,
        "ota_9_5_plus":pd.to_numeric(x.ota_score,errors="coerce").ge(9.5),
        "base_3":pd.to_numeric(x.base_candles,errors="coerce").eq(3),
        "rbr":x.pattern.astype(str).eq("RBR"),
        "dbd":x.pattern.astype(str).eq("DBD"),
    }
    for period in ["development","calibration","holdout"]:
        p=x[x.period==period]; base=float(p.massive.mean()) if len(p) else np.nan
        for name,mask in features.items():
            q=p[mask.reindex(p.index,fill_value=False)]; rate=float(q.massive.mean()) if len(q) else np.nan
            rows.append({"period":period,"feature":name,"n":len(q),"massive_entries":int(q.massive.sum()),
                         "massive_entry_rate":rate,"baseline":base,"lift":rate/base if base and len(q) else np.nan})
    return pd.DataFrame(rows)


def main() -> None:
    OUT.mkdir(parents=True,exist_ok=True)
    source=LAB/"all_session_metrics.csv"
    if not source.exists(): raise FileNotFoundError(f"Run Massive Move Lab first: {source}")
    days=pd.read_csv(source)
    zones=read_zones()
    x=attach_sessions(zones,days)
    x.to_parquet(OUT/"zone_session_link.parquet",index=False)

    matrices=[]
    matrices.append(ladder(x,["period"],"all_zones"))
    matrices.append(ladder(x,["period","massive"],"massive_vs_ordinary"))
    matrices.append(ladder(x,["period","prior_expansion"],"prior_expansion"))
    matrices.append(ladder(x,["period","gap_large"],"gap_large"))
    matrices.append(ladder(x,["period","symbol"],"symbol"))
    matrices.append(ladder(x,["period","pattern"],"pattern"))
    matrices.append(ladder(x,["period","direction_aligned"],"direction_alignment"))
    matrix=pd.concat(matrices,ignore_index=True)
    matrix.to_csv(OUT/"zone_link_1r_to_20r_matrix.csv",index=False)
    enrich=feature_enrichment(x); enrich.to_csv(OUT/"massive_move_feature_enrichment.csv",index=False)

    # Chart queue contains actual V6 setups on the strongest sessions.
    queue=x[x.massive].sort_values(["massive_score","ota_score"],ascending=False).head(1000)
    cols=[c for c in ["symbol","session_date","zone_id","entry_ts","pattern","direction","session_direction",
          "direction_aligned","ota_score","base_candles","departure_ratio","profit_room_r","entry","stop","risk",
          "max_verified_r","max_possible_r","massive_score","prior_expansion","gap_large"] if c in queue.columns]
    queue[cols].to_csv(OUT/"massive_day_v6_setup_review_queue.csv",index=False)

    report={"schema":"TP_V6_MASSIVE_ZONE_LINK_1","generated_utc":datetime.now(timezone.utc).isoformat(),
            "database_integrity":"ok","zones":len(zones),"zones_joined_to_sessions":int(x.massive_score.notna().sum()),
            "massive_day_zone_entries":int(x.massive.sum()),"cost_r":COST_R,
            "warning":"Massive-day membership is outcome information. Only point-in-time fields may become candidate rules."}
    (OUT/"zone_link_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")

    files=["zone_link_report.json","zone_link_1r_to_20r_matrix.csv","massive_move_feature_enrichment.csv",
           "massive_day_v6_setup_review_queue.csv"]
    import zipfile
    result=Path.home()/"Downloads"/"TradingPulse_V6_Massive_Move_Zone_Link_Result_20260823.zip"
    with zipfile.ZipFile(result,"w",zipfile.ZIP_DEFLATED) as zf:
        for name in files: zf.write(OUT/name,arcname=name)
    print("Trading Pulse Massive-Move / Zone Link")
    print(f"Zones: {len(zones):,}")
    print(f"Joined to sessions: {int(x.massive_score.notna().sum()):,}")
    print(f"Massive-day zone entries: {int(x.massive.sum()):,}")
    print(f"RESULT ZIP READY: {result}")


if __name__=="__main__": main()
