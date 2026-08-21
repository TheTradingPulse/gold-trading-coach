import psycopg2
import pandas as pd
from datetime import datetime, timezone


def log_trade(direction, entry, stop, target, rr_ratio, grade, alignment_score, zone_type, notes=""):
    """Log a new trade to the journal"""
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO trade_journal (timestamp, symbol, direction, entry, stop, target, rr_ratio, grade, alignment_score, zone_type, outcome, notes)
        VALUES (NOW(), 'GC', %s, %s, %s, %s, %s, %s, %s, %s, 'OPEN', %s)
        RETURNING id;
    """, (
        str(direction),
        float(entry),
        float(stop),
        float(target),
        float(rr_ratio),
        str(grade),
        float(alignment_score),
        str(zone_type),
        str(notes)
    ))

    trade_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()

    print(f"Trade #{trade_id} logged: {direction} @ ${float(entry):.2f}")
    return trade_id


def update_outcome(trade_id, outcome, exit_price):
    """Update trade outcome and calculate P&L"""
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT entry, direction FROM trade_journal WHERE id = %s", (trade_id,))
    result = cursor.fetchone()

    if not result:
        print(f"Trade #{trade_id} not found")
        cursor.close()
        conn.close()
        return

    entry = float(result[0])
    direction = result[1]

    exit_price = float(exit_price)
    if direction == "LONG":
        pnl = exit_price - entry
    else:
        pnl = entry - exit_price

    cursor.execute("""
        UPDATE trade_journal
        SET outcome = %s, exit_price = %s, pnl = %s
        WHERE id = %s
    """, (str(outcome), exit_price, round(float(pnl), 2), trade_id))

    conn.commit()
    cursor.close()
    conn.close()

    print(f"Trade #{trade_id} updated: {outcome} | P&L: ${pnl:.2f}")
    return pnl


def get_all_trades():
    """Get all trades from journal"""
    from database import get_connection
    conn = get_connection()
    query = "SELECT * FROM trade_journal ORDER BY timestamp DESC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def get_closed_trades():
    """Get only closed trades"""
    from database import get_connection
    conn = get_connection()
    query = "SELECT * FROM trade_journal WHERE outcome IN ('WIN','LOSS','BREAKEVEN') ORDER BY timestamp DESC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def calculate_statistics():
    """Calculate performance statistics"""
    df = get_closed_trades()

    if len(df) == 0:
        return None

    wins = df[df["outcome"] == "WIN"]
    losses = df[df["outcome"] == "LOSS"]
    breakeven = df[df["outcome"] == "BREAKEVEN"]

    total_trades = len(df)
    win_count = len(wins)
    loss_count = len(losses)
    be_count = len(breakeven)

    win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0
    loss_rate = (loss_count / total_trades) * 100 if total_trades > 0 else 0

    avg_win = float(wins["pnl"].mean()) if win_count > 0 else 0
    avg_loss = abs(float(losses["pnl"].mean())) if loss_count > 0 else 0
    avg_pnl = float(df["pnl"].mean()) if total_trades > 0 else 0

    total_wins_pnl = float(wins["pnl"].sum()) if win_count > 0 else 0
    total_losses_pnl = abs(float(losses["pnl"].sum())) if loss_count > 0 else 0

    profit_factor = total_wins_pnl / total_losses_pnl if total_losses_pnl > 0 else float('inf')

    expectancy = (win_rate / 100 * avg_win) - (loss_rate / 100 * avg_loss)

    avg_rr = float(df["rr_ratio"].mean()) if total_trades > 0 else 0

    cumulative = df.sort_values("timestamp")["pnl"].astype(float).cumsum()
    running_max = cumulative.cummax()
    drawdown = cumulative - running_max
    max_drawdown = float(drawdown.min())

    stats = {
        "total_trades": total_trades,
        "wins": win_count,
        "losses": loss_count,
        "breakeven": be_count,
        "win_rate": round(win_rate, 1),
        "loss_rate": round(loss_rate, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "avg_pnl": round(avg_pnl, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy": round(expectancy, 2),
        "avg_rr_achieved": round(avg_rr, 2),
        "max_drawdown": round(max_drawdown, 2),
        "total_pnl": round(float(df["pnl"].sum()), 2)
    }

    return stats


def display_statistics():
    """Display performance statistics in formatted view"""
    stats = calculate_statistics()

    if stats is None:
        return

    print("\n" + "=" * 50)
    print("   TRADE PERFORMANCE STATISTICS")
    print("=" * 50)
    print(f"  Total Trades:     {stats['total_trades']}")
    print(f"  Wins:             {stats['wins']}")
    print(f"  Losses:           {stats['losses']}")
    print(f"  Breakeven:        {stats['breakeven']}")
    print(f"  Win Rate:         {stats['win_rate']}%")
    print(f"  Loss Rate:        {stats['loss_rate']}%")
    print(f"  Average Win:      ${stats['avg_win']:.2f}")
    print(f"  Average Loss:     ${stats['avg_loss']:.2f}")
    print(f"  Profit Factor:    {stats['profit_factor']}")
    print(f"  Expectancy:       ${stats['expectancy']:.2f}")
    print(f"  Avg R:R Achieved: {stats['avg_rr_achieved']}:1")
    print(f"  Max Drawdown:     ${stats['max_drawdown']:.2f}")
    print(f"  Total P&L:        ${stats['total_pnl']:.2f}")
    print("=" * 50)

    print("\n--- KPI Assessment ---")
    if stats['total_trades'] < 10:
        print("⚠️  Less than 10 trades - not statistically significant yet")

    if stats['win_rate'] >= 40:
        print(f"✅ Win Rate {stats['win_rate']}% - meets 40% target")
    else:
        print(f"❌ Win Rate {stats['win_rate']}% - below 40% target")

    if stats['profit_factor'] >= 1.5:
        print(f"✅ Profit Factor {stats['profit_factor']} - meets 1.5 target")
    else:
        print(f"❌ Profit Factor {stats['profit_factor']} - below 1.5 target")

    if stats['expectancy'] > 0:
        print(f"✅ Positive Expectancy: ${stats['expectancy']:.2f} per trade")
    else:
        print(f"❌ Negative Expectancy: ${stats['expectancy']:.2f} per trade")


def show_recent_trades(limit=10):
    """Display recent trades"""
    df = get_all_trades()

    if len(df) == 0:
        print("\nNo trades in journal yet.")
        return

    df = df.head(limit)

    print(f"\n--- Recent Trades (Last {len(df)}) ---")
    for _, trade in df.iterrows():
        outcome = str(trade["outcome"])
        status = "🟢" if outcome == "WIN" else "🔴" if outcome == "LOSS" else "⚪" if outcome == "BREAKEVEN" else "🟡"
        pnl_val = trade["pnl"]
        pnl_str = f"${float(pnl_val):.2f}" if pnl_val is not None and str(pnl_val) != 'nan' and str(pnl_val) != 'None' else "---"
        print(f"  {status} #{trade['id']}: {trade['direction']} | Grade: {trade['grade']} | Entry: ${float(trade['entry']):.2f} | Outcome: {outcome} | P&L: {pnl_str}")


if __name__ == "__main__":
    display_statistics()
    show_recent_trades()