import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "analysis"))
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import numpy as np
from database import get_connection
import psycopg2
from datetime import datetime, timedelta

from trend_engine import assess_trend
from zone_engine import detect_supply_zones, detect_demand_zones, is_price_near_zone


def load_full_history(timeframe="D"):
    conn = get_connection()
    query = """
        SELECT timestamp, open, high, low, close, volume
        FROM gold_ohlcv
        WHERE timeframe = %s
        ORDER BY timestamp ASC
    """
    df = pd.read_sql_query(query, conn, params=(timeframe,))
    conn.close()
    if len(df) == 0:
        return None
    df = df.set_index("timestamp")
    df = df.sort_index()
    return df


def get_available_years():
    conn = get_connection()
    query = """
        SELECT DISTINCT EXTRACT(YEAR FROM timestamp) as year
        FROM gold_ohlcv
        WHERE timeframe = 'D'
        ORDER BY year
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    if len(df) == 0:
        return []
    return [int(y) for y in df["year"].tolist()]


def get_available_timeframes():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT timeframe FROM gold_ohlcv ORDER BY timeframe")
    tfs = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return tfs


def check_data_available(timeframe, start_date, end_date):
    conn = get_connection()
    query = """
        SELECT COUNT(*) FROM gold_ohlcv
        WHERE timeframe = %s
        AND timestamp >= %s
        AND timestamp <= %s
    """
    cur = conn.cursor()
    cur.execute(query, (timeframe, start_date, end_date))
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count > 100


def import_yahoo_gold_extended():
    try:
        import yfinance as yf
        print("Downloading Gold data from Yahoo Finance...")
        gold = yf.download("GC=F", period="max", interval="1d", progress=False)
        if gold.empty:
            return False
        gold.columns = gold.columns.get_level_values(0)
        gold = gold.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        gold = gold.reset_index()
        gold["timeframe"] = "D"
        gold["timestamp"] = pd.to_datetime(gold["Date"]).dt.tz_localize(None)
        gold = gold.drop(columns=["Date"])
        conn = get_connection()
        cur = conn.cursor()
        rows = 0
        for _, row in gold.iterrows():
            try:
                cur.execute("""
                    INSERT INTO gold_ohlcv (timeframe, timestamp, open, high, low, close, volume)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (timeframe, timestamp) DO UPDATE
                    SET open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low, close = EXCLUDED.close, volume = EXCLUDED.volume
                """, (row["timeframe"], row["timestamp"],
                    float(row["open"]) if pd.notna(row["open"]) else None,
                    float(row["high"]) if pd.notna(row["high"]) else None,
                    float(row["low"]) if pd.notna(row["low"]) else None,
                    float(row["close"]) if pd.notna(row["close"]) else None,
                    float(row["volume"]) if pd.notna(row["volume"]) else 0))
                rows += 1
            except:
                pass
        conn.commit()
        cur.close()
        conn.close()
        print(f"Imported {rows} daily candles")
        return True
    except Exception as e:
        print(f"Import failed: {e}")
        return False


def run_backtest(
    start_date=None, end_date=None,
    initial_capital=10000, risk_per_trade=0.02,
    zone_timeframe="D", entry_timeframe="D", trend_timeframe="D",
    session_start=0, session_end=23,
    cooldown_hours=24, zone_max_age_hours=720,
    min_zone_strength=15, max_risk_pct=0.02,
    use_trailing_stop=False, trend_mode="OR"
):
    print("=" * 70)
    print("   GOLD TRADING COACH - SMART BACKTEST")
    print("=" * 70)

    has_zone_data = check_data_available(zone_timeframe, start_date, end_date)
    has_entry_data = check_data_available(entry_timeframe, start_date, end_date)
    has_trend_data = check_data_available(trend_timeframe, start_date, end_date)

    if not has_zone_data:
        print(f"WARNING: No {zone_timeframe} data. Falling back to Daily.")
        zone_timeframe = "D"
    if not has_entry_data:
        print(f"WARNING: No {entry_timeframe} data. Falling back to Daily.")
        entry_timeframe = "D"
    if not has_trend_data:
        print(f"WARNING: No {trend_timeframe} data. Falling back to Daily.")
        trend_timeframe = "D"

    print(f"Using: Zones={zone_timeframe} | Entries={entry_timeframe} | Trend={trend_timeframe}")

    daily_data = load_full_history(trend_timeframe)
    zone_data = load_full_history(zone_timeframe)
    entry_data = load_full_history(entry_timeframe)

    if daily_data is None or entry_data is None or zone_data is None:
        print("ERROR: No data available.")
        return None

    if start_date:
        try:
            start_ts = pd.Timestamp(str(start_date))
            if daily_data.index.tz is not None:
                start_ts = start_ts.tz_localize('UTC')
            daily_data = daily_data[daily_data.index >= start_ts]
            zone_data = zone_data[zone_data.index >= start_ts]
            entry_data = entry_data[entry_data.index >= start_ts]
        except:
            pass
    if end_date:
        try:
            end_ts = pd.Timestamp(str(end_date))
            if daily_data.index.tz is not None:
                end_ts = end_ts.tz_localize('UTC')
            daily_data = daily_data[daily_data.index <= end_ts]
            zone_data = zone_data[zone_data.index <= end_ts]
            entry_data = entry_data[entry_data.index <= end_ts]
        except:
            pass

    if len(daily_data) < 50 or len(zone_data) < 50 or len(entry_data) < 50:
        print("ERROR: Not enough data after filtering.")
        return None

    print(f"Period: {daily_data.index[0].date()} to {daily_data.index[-1].date()}")
    print(f"Candles - Trend: {len(daily_data)} | Zones: {len(zone_data)} | Entries: {len(entry_data)}")
    print(f"Capital: ${initial_capital:,.0f} | Risk: {risk_per_trade*100:.0f}%/trade")

    trades = []
    capital = initial_capital
    equity_curve = []
    open_trade = None
    cooldown_until = None
    trailing_activated = False
    trailing_stop = None

    window_size = 50
    total = len(entry_data) - 1

    for i in range(window_size, total):
        current_time = entry_data.index[i]
        current_price = float(entry_data["close"].iloc[i])
        current_high = float(entry_data["high"].iloc[i])
        current_low = float(entry_data["low"].iloc[i])

        current_hour = current_time.hour
        if current_hour < session_start or current_hour > session_end:
            equity_curve.append({"time": current_time, "equity": capital})
            continue

        trend_window = daily_data[daily_data.index <= current_time].tail(50)
        if len(trend_window) < 30:
            continue
        main_trend = assess_trend(trend_window)

        trend_bullish = (main_trend == "bullish")
        trend_bearish = (main_trend == "bearish")

        if open_trade:
            trade = open_trade
            if trade["direction"] == "LONG":
                if use_trailing_stop and trailing_activated and trailing_stop:
                    if current_low <= trailing_stop:
                        trade.update({"exit_time": current_time, "exit_price": trailing_stop,
                                      "outcome": "WIN" if trailing_stop > trade["entry"] else "LOSS",
                                      "pnl": trailing_stop - trade["entry"]})
                        trades.append(trade)
                        ps = (capital * risk_per_trade) / abs(trade["entry"] - trade["stop"])
                        capital += trade["pnl"] * ps
                        open_trade = None
                        cooldown_until = current_time + timedelta(hours=cooldown_hours)
                        trailing_activated = False
                        trailing_stop = None
                        continue
                if not trailing_activated and use_trailing_stop:
                    risk_amount = trade["entry"] - trade["stop"]
                    if current_high >= trade["entry"] + risk_amount * 2:
                        trailing_activated = True
                        trailing_stop = trade["entry"] + risk_amount
                if trailing_activated and use_trailing_stop:
                    risk_amount = trade["entry"] - trade["stop"]
                    new_trail = current_high - risk_amount
                    if new_trail > trailing_stop:
                        trailing_stop = new_trail
                if current_low <= trade["stop"]:
                    trade.update({"exit_time": current_time, "exit_price": trade["stop"],
                                  "outcome": "LOSS", "pnl": trade["stop"] - trade["entry"]})
                    trades.append(trade)
                    ps = (capital * risk_per_trade) / abs(trade["entry"] - trade["stop"])
                    capital += trade["pnl"] * ps
                    open_trade = None
                    cooldown_until = current_time + timedelta(hours=cooldown_hours)
                    trailing_activated = False
                    trailing_stop = None
                    continue
            elif trade["direction"] == "SHORT":
                if use_trailing_stop and trailing_activated and trailing_stop:
                    if current_high >= trailing_stop:
                        trade.update({"exit_time": current_time, "exit_price": trailing_stop,
                                      "outcome": "WIN" if trailing_stop < trade["entry"] else "LOSS",
                                      "pnl": trade["entry"] - trailing_stop})
                        trades.append(trade)
                        ps = (capital * risk_per_trade) / abs(trade["entry"] - trade["stop"])
                        capital += trade["pnl"] * ps
                        open_trade = None
                        cooldown_until = current_time + timedelta(hours=cooldown_hours)
                        trailing_activated = False
                        trailing_stop = None
                        continue
                if not trailing_activated and use_trailing_stop:
                    risk_amount = trade["stop"] - trade["entry"]
                    if current_low <= trade["entry"] - risk_amount * 2:
                        trailing_activated = True
                        trailing_stop = trade["entry"] - risk_amount
                if trailing_activated and use_trailing_stop:
                    risk_amount = trade["stop"] - trade["entry"]
                    new_trail = current_low + risk_amount
                    if new_trail < trailing_stop:
                        trailing_stop = new_trail
                if current_high >= trade["stop"]:
                    trade.update({"exit_time": current_time, "exit_price": trade["stop"],
                                  "outcome": "LOSS", "pnl": trade["entry"] - trade["stop"]})
                    trades.append(trade)
                    ps = (capital * risk_per_trade) / abs(trade["entry"] - trade["stop"])
                    capital += trade["pnl"] * ps
                    open_trade = None
                    cooldown_until = current_time + timedelta(hours=cooldown_hours)
                    trailing_activated = False
                    trailing_stop = None
                    continue

        equity_curve.append({"time": current_time, "equity": capital})

        if open_trade or (cooldown_until and current_time < cooldown_until):
            continue

        zone_window = zone_data[zone_data.index <= current_time].tail(50)
        if len(zone_window) < 30:
            continue

        demand_zones = detect_demand_zones(zone_window)
        supply_zones = detect_supply_zones(zone_window)

        near_demand = [z for z in demand_zones if is_price_near_zone(current_price, z, 0.5)]
        near_supply = [z for z in supply_zones if is_price_near_zone(current_price, z, 0.5)]

        if trend_bullish and near_demand:
            zone = near_demand[-1]
            zone_time = pd.Timestamp(zone["created_at"])
            if (current_time - zone_time).total_seconds() / 3600 > zone_max_age_hours:
                continue
            if zone["strength"] < min_zone_strength:
                continue
            entry = current_price
            stop = zone["lower_bound"] * 0.998
            risk = entry - stop
            if risk <= 0 or risk > current_price * max_risk_pct:
                continue
            open_trade = {"direction": "LONG", "entry": entry, "stop": stop,
                          "entry_time": current_time, "zone_strength": zone["strength"]}
            trailing_activated = False
            trailing_stop = None

        elif trend_bearish and near_supply:
            zone = near_supply[-1]
            zone_time = pd.Timestamp(zone["created_at"])
            if (current_time - zone_time).total_seconds() / 3600 > zone_max_age_hours:
                continue
            if zone["strength"] < min_zone_strength:
                continue
            entry = current_price
            stop = zone["upper_bound"] * 1.002
            risk = stop - entry
            if risk <= 0 or risk > current_price * max_risk_pct:
                continue
            open_trade = {"direction": "SHORT", "entry": entry, "stop": stop,
                          "entry_time": current_time, "zone_strength": zone["strength"]}
            trailing_activated = False
            trailing_stop = None

        if i % 5000 == 0:
            print(f"  {i}/{total}")

    if open_trade:
        trade = open_trade
        trade["exit_time"] = entry_data.index[-1]
        trade["exit_price"] = float(entry_data["close"].iloc[-1])
        trade["pnl"] = trade["exit_price"] - trade["entry"] if trade["direction"] == "LONG" else trade["entry"] - trade["exit_price"]
        trade["outcome"] = "WIN" if trade["pnl"] > 0 else "LOSS"
        trades.append(trade)
        ps = (capital * risk_per_trade) / abs(trade["entry"] - trade["stop"])
        capital += trade["pnl"] * ps

    return calculate_stats(trades, equity_curve, initial_capital, capital)


def calculate_stats(trades, equity_curve, initial_capital, final_capital):
    if not trades:
        return None

    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity_curve)

    wins = trades_df[trades_df["outcome"] == "WIN"]
    losses = trades_df[trades_df["outcome"] == "LOSS"]

    total_trades = len(trades_df)
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0

    avg_win = float(wins["pnl"].mean()) if win_count > 0 else 0
    avg_loss = abs(float(losses["pnl"].mean())) if loss_count > 0 else 0

    total_profit = float(wins["pnl"].sum()) if win_count > 0 else 0
    total_loss = abs(float(losses["pnl"].sum())) if loss_count > 0 else 0
    profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

    expectancy = (win_rate/100 * avg_win) - ((100-win_rate)/100 * avg_loss)

    equity_df["peak"] = equity_df["equity"].cummax()
    equity_df["drawdown"] = equity_df["equity"] - equity_df["peak"]
    equity_df["drawdown_pct"] = (equity_df["drawdown"] / equity_df["peak"]) * 100
    max_dd_pct = float(equity_df["drawdown_pct"].min())

    total_return = ((final_capital - initial_capital) / initial_capital) * 100

    trades_df_copy = trades_df.copy()
    trades_df_copy["entry_time_dt"] = pd.to_datetime(trades_df_copy["entry_time"]).dt.tz_localize(None)
    trades_df_copy["month"] = trades_df_copy["entry_time_dt"].dt.to_period("M")
    monthly = trades_df_copy.groupby("month").agg(
        trades=("pnl", "count"),
        wins=("outcome", lambda x: (x == "WIN").sum()),
        pnl=("pnl", "sum")
    )

    trades_df_copy["year"] = trades_df_copy["entry_time_dt"].dt.year
    yearly = trades_df_copy.groupby("year").agg(
        trades=("pnl", "count"),
        wins=("outcome", lambda x: (x == "WIN").sum()),
        pnl=("pnl", "sum")
    )

    winning_months = len(monthly[monthly["pnl"] > 0])
    total_months = len(monthly)

    print(f"\n  Trades: {total_trades} | Wins: {win_count} | Losses: {loss_count}")
    print(f"  Win Rate: {win_rate:.1f}% | PF: {profit_factor:.2f} | Expectancy: ${expectancy:.2f}")
    print(f"  Return: {total_return:.1f}% | Max DD: {max_dd_pct:.1f}% | Final: ${final_capital:,.0f}")

    return {
        "trades": trades_df,
        "equity_curve": equity_df,
        "monthly": monthly,
        "yearly": yearly,
        "stats": {
            "total_trades": total_trades,
            "wins": win_count,
            "losses": loss_count,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "expectancy": expectancy,
            "total_return": total_return,
            "max_drawdown": max_dd_pct,
            "final_capital": final_capital,
            "winning_months": winning_months,
            "total_months": total_months
        }
    }


if __name__ == "__main__":
    import_yahoo_gold_extended()
    years = get_available_years()
    print(f"Available: {years[0]}-{years[-1]}" if years else "No data")