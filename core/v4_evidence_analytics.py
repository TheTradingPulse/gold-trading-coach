import json, sqlite3
from pathlib import Path

def _bucket():
    return """CASE
        WHEN score10<6 THEN '<6'
        WHEN score10<7 THEN '6-6.9'
        WHEN score10<8 THEN '7-7.9'
        WHEN score10<8.5 THEN '8-8.4'
        WHEN score10<9 THEN '8.5-8.9'
        ELSE '9+'
    END"""

def evidence_report(path="research_data/v4/evidence_v3.db"):
    if not Path(path).exists():
        return {}
    with sqlite3.connect(path) as d:
        d.row_factory = sqlite3.Row
        def rows(q):
            return [dict(x) for x in d.execute(q)]

        integrity = rows("""SELECT
            COUNT(*) rows,
            COUNT(DISTINCT evidence_key) unique_keys,
            SUM(score10<0 OR score10>10) bad_scores,
            SUM(entered=1 AND (alive_mfe_r IS NULL OR alive_mae_r IS NULL)) missing_normalized,
            SUM(entered=1 AND risk_points<=0) bad_risk,
            SUM(entered=1 AND alive_mae_r < -1.000001) alive_mae_below_stop,
            SUM(realized_r < -1.000001) realized_below_stop,
            SUM(same_bar_ambiguous) ambiguous
        FROM observations""")[0]

        by_symbol = rows("""SELECT symbol,
            COUNT(*) observations,
            SUM(entered) triggered,
            ROUND(100.0*SUM(entered)/COUNT(*),1) trigger_pct,
            SUM(primary_hit) hit_3r,
            SUM(stretch_hit) hit_5r,
            ROUND(100.0*SUM(primary_hit)/NULLIF(SUM(entered),0),1) hit_3r_pct_of_triggered,
            ROUND(100.0*SUM(stretch_hit)/NULLIF(SUM(entered),0),1) hit_5r_pct_of_triggered,
            ROUND(100.0*SUM(CASE WHEN primary_hit=1 AND stretch_hit=1 THEN 1 ELSE 0 END)/NULLIF(SUM(primary_hit),0),1) five_after_three_pct,
            SUM(stop_hit) stops,
            ROUND(AVG(score10),2) avg_score10,
            ROUND(AVG(CASE WHEN entered=1 THEN alive_mfe_r END),2) avg_alive_mfe_r,
            ROUND(AVG(CASE WHEN entered=1 THEN alive_mae_r END),2) avg_alive_mae_r,
            ROUND(AVG(CASE WHEN entered=1 THEN raw_mfe_r END),2) avg_raw_mfe_r,
            ROUND(AVG(CASE WHEN entered=1 THEN raw_mae_r END),2) avg_raw_mae_r
        FROM observations GROUP BY symbol ORDER BY symbol""")

        buckets = rows(f"""SELECT symbol,{_bucket()} bucket,
            COUNT(*) n,
            SUM(entered) triggered,
            ROUND(100.0*SUM(entered)/COUNT(*),1) trigger_pct,
            SUM(primary_hit) hit_3r,
            SUM(stretch_hit) hit_5r,
            ROUND(100.0*SUM(primary_hit)/NULLIF(SUM(entered),0),1) hit_3r_pct,
            ROUND(100.0*SUM(stretch_hit)/NULLIF(SUM(entered),0),1) hit_5r_pct,
            ROUND(AVG(CASE WHEN entered=1 THEN alive_mfe_r END),2) avg_alive_mfe_r,
            ROUND(AVG(CASE WHEN entered=1 THEN alive_mae_r END),2) avg_alive_mae_r,
            ROUND(AVG(CASE WHEN entered=1 THEN raw_mfe_r END),2) avg_raw_mfe_r,
            ROUND(AVG(CASE WHEN entered=1 THEN raw_mae_r END),2) avg_raw_mae_r
        FROM observations GROUP BY symbol,bucket ORDER BY symbol,bucket""")

        setup_types = rows("""SELECT symbol,setup_type,direction,
            COUNT(*) n,SUM(entered) triggered,SUM(primary_hit) hit_3r,SUM(stretch_hit) hit_5r,
            ROUND(AVG(score10),2) avg_score10,
            ROUND(AVG(CASE WHEN entered=1 THEN alive_mfe_r END),2) avg_alive_mfe_r,
            ROUND(AVG(CASE WHEN entered=1 THEN alive_mae_r END),2) avg_alive_mae_r
        FROM observations GROUP BY symbol,setup_type,direction
        HAVING COUNT(*)>=5 ORDER BY symbol,n DESC""")

        risk_width = rows("""SELECT symbol,
            ROUND(MIN(risk_points),4) min_risk,
            ROUND(AVG(risk_points),4) avg_risk,
            ROUND(MAX(risk_points),4) max_risk,
            SUM(CASE WHEN risk_points IS NOT NULL AND risk_points>0 THEN 1 ELSE 0 END) valid_risk_rows
        FROM observations GROUP BY symbol ORDER BY symbol""")

    return {
        "integrity":integrity,
        "by_symbol":by_symbol,
        "score_buckets":buckets,
        "setup_type_direction":setup_types,
        "risk_width":risk_width
    }

def report(path="research_data/v4/evidence_v3.db"):
    return evidence_report(path)

def print_report(path="research_data/v4/evidence_v3.db"):
    print(json.dumps(evidence_report(path),indent=2))
