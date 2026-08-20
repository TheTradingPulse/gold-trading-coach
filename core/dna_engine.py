import pandas as pd
import psycopg2
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from datetime import datetime


def generate_trade_tags(direction, zone_type, alignment_score, grade, timeframe=None):
    """Generate DNA tags for a trade based on its characteristics."""
    tags = []

    if zone_type == "demand":
        tags.append("Demand Zone")
    elif zone_type == "supply":
        tags.append("Supply Zone")

    if direction == "LONG":
        tags.append("Long Trade")
    else:
        tags.append("Short Trade")

    if alignment_score >= 80:
        tags.append("High Alignment")
    elif alignment_score >= 60:
        tags.append("Moderate Alignment")
    else:
        tags.append("Low Alignment")

    tags.append(f"Grade {grade}")

    if timeframe:
        tags.append(f"TF {timeframe}")

    now = datetime.now()
    hour = now.hour
    if hour < 9:
        tags.append("Asian Session")
    elif hour < 12:
        tags.append("Morning Session")
    elif hour < 17:
        tags.append("Afternoon Session")
    else:
        tags.append("Evening Session")

    day_name = now.strftime("%A")
    tags.append(day_name)

    from news_engine import get_event_tags
    news_tags = get_event_tags()
    tags.extend(news_tags)

    from trade_engine import get_trends
    trends = get_trends()
    d_trend = trends.get("D", "neutral")

    if direction == "LONG" and d_trend == "bearish":
        tags.append("Countertrend")
    elif direction == "SHORT" and d_trend == "bullish":
        tags.append("Countertrend")
    else:
        tags.append("Trend Trade")

    return tags


def save_trade_dna(trade_id, tags):
    """Save DNA tags for a trade"""
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()

    for tag in tags:
        try:
            cursor.execute("""
                INSERT INTO trade_dna (trade_id, tag)
                VALUES (%s, %s)
                ON CONFLICT (trade_id, tag) DO NOTHING
            """, (trade_id, tag))
        except Exception:
            pass

    tags_string = ", ".join(tags)
    cursor.execute("UPDATE trade_journal SET tags = %s WHERE id = %s", (tags_string, trade_id))
    conn.commit()
    cursor.close()
    conn.close()

    print(f"DNA tags saved for Trade #{trade_id}: {tags_string}")
    return tags


def log_trade_with_dna(direction, entry, stop, target, rr_ratio, grade, alignment_score, zone_type, timeframe=None, notes=""):
    """Log a trade AND generate/save DNA tags in one step"""
    from journal_engine import log_trade

    trade_id = log_trade(direction, entry, stop, target, rr_ratio, grade, alignment_score, zone_type, notes)
    tags = generate_trade_tags(direction, zone_type, alignment_score, grade, timeframe)
    save_trade_dna(trade_id, tags)

    return trade_id, tags


def get_dna_tags(trade_id):
    """Get all DNA tags for a trade"""
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT tag FROM trade_dna WHERE trade_id = %s ORDER BY tag", (trade_id,))
    tags = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return tags


def analyze_dna_performance():
    """Analyze which DNA tags perform best"""
    from database import get_connection
    conn = get_connection()

    query = """
        SELECT 
            td.tag,
            COUNT(*) as total_trades,
            SUM(CASE WHEN tj.outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN tj.outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
            ROUND(AVG(CASE WHEN tj.pnl IS NOT NULL THEN tj.pnl ELSE 0 END)::numeric, 2) as avg_pnl,
            ROUND(SUM(CASE WHEN tj.outcome = 'WIN' THEN 1 ELSE 0 END)::decimal / COUNT(*)::decimal * 100, 1) as win_rate
        FROM trade_dna td
        JOIN trade_journal tj ON td.trade_id = tj.id
        WHERE tj.outcome != 'OPEN'
        GROUP BY td.tag
        HAVING COUNT(*) >= 1
        ORDER BY avg_pnl DESC
    """

    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def display_dna_analysis():
    """Display DNA performance analysis"""
    df = analyze_dna_performance()

    if len(df) == 0:
        print("\nNot enough closed trades for DNA analysis.")
        return

    print("\n" + "=" * 70)
    print("   TRADE DNA ANALYSIS - Which Setups Perform Best?")
    print("=" * 70)
    print(f"{'Tag':<30} {'Trades':>7} {'Wins':>5} {'Win%':>7} {'Avg P&L':>10}")
    print("-" * 70)

    for _, row in df.iterrows():
        print(f"{row['tag']:<30} {row['total_trades']:>7} {row['wins']:>5} {row['win_rate']:>6.1f}% ${row['avg_pnl']:>9.2f}")

    print("=" * 70)

    top = df[df['win_rate'] >= 50].head(5)
    if len(top) > 0:
        print("\n🏆 TOP PERFORMING TAGS:")
        for _, row in top.iterrows():
            print(f"  ✅ {row['tag']}: {row['win_rate']}% win rate, Avg P&L: ${row['avg_pnl']:.2f}")

    bottom = df[df['win_rate'] < 40].head(5)
    if len(bottom) > 0:
        print("\n⚠️ WORST PERFORMING TAGS:")
        for _, row in bottom.iterrows():
            print(f"  ❌ {row['tag']}: {row['win_rate']}% win rate, Avg P&L: ${row['avg_pnl']:.2f}")


if __name__ == "__main__":
    from journal_engine import get_all_trades
    trades = get_all_trades()

    if len(trades) > 0:
        print("Generating DNA tags for existing trades...\n")
        for _, trade in trades.iterrows():
            existing = get_dna_tags(int(trade['id']))
            if not existing:
                tags = generate_trade_tags(
                    direction=str(trade['direction']),
                    zone_type="demand" if "demand" in str(trade.get('notes', '')).lower() else "supply",
                    alignment_score=float(trade['alignment_score']),
                    grade=str(trade['grade'])
                )
                save_trade_dna(int(trade['id']), tags)

    display_dna_analysis()