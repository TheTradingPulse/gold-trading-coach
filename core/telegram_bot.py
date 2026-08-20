import asyncio
import sys
import threading
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "analysis"))
sys.path.insert(0, str(Path(__file__).parent))

from database import get_connection
from trade_engine import get_current_price, get_trends, calculate_alignment, grade_setup
from zone_engine import load_data, detect_supply_zones, detect_demand_zones, is_price_near_zone
from journal_engine import calculate_statistics, get_all_trades
from ai_explainer import generate_explanation, generate_market_summary
from news_engine import generate_news_warning, get_confidence_adjustment, display_news_calendar
from live_data_engine import quick_refresh, get_data_source_name
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
import os
from dotenv import load_dotenv
from datetime import datetime
from io import StringIO

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def refresh_data():
    """Refresh market data quickly before answering."""
    try:
        quick_refresh()
        return True
    except Exception as e:
        print(f"Data refresh failed: {e}")
        return False


def background_refresh():
    """Background task that refreshes data every 5 minutes."""
    while True:
        time.sleep(300)  # 300 seconds = 5 minutes
        try:
            quick_refresh()
            print("Auto-refresh completed")
        except Exception as e:
            print(f"Auto-refresh error: {e}")


# Start background refresh thread
thread = threading.Thread(target=background_refresh, daemon=True)
thread.start()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = f"""
🥇 *Gold Trading Coach*

Welcome! I help you analyze Gold Futures (GC) with:
• Multi-timeframe trend analysis
• Supply & demand zones
• Trade opportunity scanning

*Commands:*
/trends - Trend analysis
/scan - Scan for trades
/market - Market summary
/zones - Active zones
/stats - Your performance
/journal - Recent trades
/news - Economic calendar
/help - Show this message

Data: {get_data_source_name()}
"""
    await update.message.reply_text(welcome, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_command(update, context)


async def trends_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Refreshing data...")
    refresh_data()
    trends = get_trends()
    direction, alignment = calculate_alignment(trends)
    current_price = get_current_price()

    message = f"📈 *GOLD TREND ANALYSIS*\n\n"
    message += f"💰 Price: ${current_price:.2f}\n"
    message += f"📊 Bias: {direction.upper()} ({alignment:.0f}%)\n\n"
    message += "*Timeframes:*\n"

    for tf in ["M", "W", "D", "4H", "1H", "15m", "5m", "1m"]:
        t = trends.get(tf, "no_data")
        emoji = "🟢" if t == "bullish" else "🔴" if t == "bearish" else "⚪"
        message += f"{emoji} {tf}: {t}\n"

    if alignment >= 60:
        message += "\n✅ Alignment sufficient for trades"
    else:
        message += "\n⚠️ Alignment below 60% - be cautious"

    await update.message.reply_text(message, parse_mode="Markdown")


async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Refreshing data...")
    refresh_data()
    await update.message.reply_text("🔍 Scanning for trade opportunities...")

    current_price = get_current_price()
    trends = get_trends()
    direction, alignment = calculate_alignment(trends)

    if alignment < 60:
        message = f"⚠️ *Alignment Too Low*\n\n"
        message += f"Current: {alignment:.0f}% | Required: 60%\n"
        message += f"Direction: {direction.upper()}\n\n"
        message += "No trades recommended right now."
        await update.message.reply_text(message, parse_mode="Markdown")
        return

    opportunities = []
    for tf in ["1H", "15m"]:
        df = load_data(tf, limit=300)
        if df is None or len(df) < 10:
            continue

        demand_zones = detect_demand_zones(df)
        supply_zones = detect_supply_zones(df)
        price = df["close"].iloc[-1]

        near_demand = [z for z in demand_zones if is_price_near_zone(price, z, 0.5)]
        near_supply = [z for z in supply_zones if is_price_near_zone(price, z, 0.5)]

        if direction == "bullish" and near_demand:
            for zone in near_demand[-2:]:
                entry = price
                stop = zone["lower_bound"] * 0.998
                risk = entry - stop
                target = entry + (risk * 3)
                grade = grade_setup(alignment, zone["strength"])
                opportunities.append({
                    "direction": "LONG",
                    "entry": entry,
                    "stop": stop,
                    "target": target,
                    "grade": grade,
                    "tf": tf,
                    "zone": zone,
                    "alignment": alignment
                })

        if direction == "bearish" and near_supply:
            for zone in near_supply[-2:]:
                entry = price
                stop = zone["upper_bound"] * 1.002
                risk = stop - entry
                target = entry - (risk * 3)
                grade = grade_setup(alignment, zone["strength"])
                opportunities.append({
                    "direction": "SHORT",
                    "entry": entry,
                    "stop": stop,
                    "target": target,
                    "grade": grade,
                    "tf": tf,
                    "zone": zone,
                    "alignment": alignment
                })

    if not opportunities:
        await update.message.reply_text("⚪ No trade opportunities found. Price not near any zones.")
        return

    for trade in opportunities:
        emoji = "🟢" if trade["direction"] == "LONG" else "🔴"
        message = f"{emoji} *{trade['direction']} SIGNAL* | Grade: {trade['grade']}\n\n"
        message += "━━━━━━━━━━━━━━━\n"
        message += f"💰 Entry: ${trade['entry']:.2f}\n"
        message += f"🛑 Stop: ${trade['stop']:.2f}\n"
        message += f"🎯 Target: ${trade['target']:.2f}\n"
        message += "📊 R:R: 3:1\n"
        message += "━━━━━━━━━━━━━━━\n\n"
        message += f"Timeframe: {trade['tf']}\n"
        message += f"Alignment: {trade['alignment']:.0f}%\n"
        message += f"Zone: ${trade['zone']['lower_bound']:.2f} - ${trade['zone']['upper_bound']:.2f}\n\n"
        message += "⚠️ Not financial advice."
        await update.message.reply_text(message, parse_mode="Markdown")


async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Refreshing data...")
    refresh_data()
    summary = generate_market_summary()
    warning, level = generate_news_warning()
    if level != "CLEAR":
        summary += f"\n\n⚠️ *News Alert:* {warning}"
    await update.message.reply_text(summary, parse_mode="Markdown")


async def zones_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Refreshing data...")
    refresh_data()
    df = load_data("1H", limit=300)
    if df is None:
        await update.message.reply_text("No data available.")
        return

    current_price = df["close"].iloc[-1]
    supply = detect_supply_zones(df)
    demand = detect_demand_zones(df)

    near_supply = [z for z in supply if is_price_near_zone(current_price, z, 1.0)]
    near_demand = [z for z in demand if is_price_near_zone(current_price, z, 1.0)]

    message = "🗺️ *SUPPLY & DEMAND ZONES (1H)*\n\n"
    message += f"💰 Current Price: ${current_price:.2f}\n\n"

    message += "🔴 *Active Supply Zones:*\n"
    if near_supply:
        for z in near_supply[-3:]:
            message += f"• ${z['lower_bound']:.2f} - ${z['upper_bound']:.2f} (S:{z['strength']})\n"
    else:
        message += "• None near price\n"

    message += "\n🟢 *Active Demand Zones:*\n"
    if near_demand:
        for z in near_demand[-3:]:
            message += f"• ${z['lower_bound']:.2f} - ${z['upper_bound']:.2f} (S:{z['strength']})\n"
    else:
        message += "• None near price\n"

    await update.message.reply_text(message, parse_mode="Markdown")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = calculate_statistics()
    if stats is None:
        await update.message.reply_text("No closed trades yet.")
        return

    message = "📊 *PERFORMANCE STATISTICS*\n\n"
    message += f"Total Trades: {stats['total_trades']}\n"
    message += f"Wins: {stats['wins']} | Losses: {stats['losses']} | BE: {stats['breakeven']}\n"
    message += f"Win Rate: {stats['win_rate']}%\n"
    message += f"Profit Factor: {stats['profit_factor']}\n"
    message += f"Expectancy: ${stats['expectancy']:.2f}\n"
    message += f"Avg Win: ${stats['avg_win']:.2f}\n"
    message += f"Avg Loss: ${stats['avg_loss']:.2f}\n"
    message += f"Max DD: ${stats['max_drawdown']:.2f}\n"
    message += f"Total P&L: ${stats['total_pnl']:.2f}\n"

    message += "\n*KPI Status:*\n"
    if stats['win_rate'] >= 40:
        message += "✅ Win Rate > 40%\n"
    else:
        message += "❌ Win Rate < 40%\n"
    if stats['profit_factor'] >= 1.5:
        message += "✅ Profit Factor > 1.5\n"
    else:
        message += "❌ Profit Factor < 1.5\n"
    if stats['expectancy'] > 0:
        message += "✅ Positive Expectancy\n"
    else:
        message += "❌ Negative Expectancy\n"

    await update.message.reply_text(message, parse_mode="Markdown")


async def journal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    trades = get_all_trades()
    if len(trades) == 0:
        await update.message.reply_text("No trades in journal yet.")
        return

    message = "📝 *RECENT TRADES*\n\n"
    for _, trade in trades.head(5).iterrows():
        outcome = str(trade["outcome"])
        emoji = "🟢" if outcome == "WIN" else "🔴" if outcome == "LOSS" else "⚪" if outcome == "BREAKEVEN" else "🟡"
        pnl = f"${float(trade['pnl']):.2f}" if trade['pnl'] and str(trade['pnl']) != 'nan' else "---"
        message += f"{emoji} #{trade['id']}: {trade['direction']} | {trade['grade']}\n"
        message += f"   Entry: ${float(trade['entry']):.2f} | Outcome: {outcome} | P&L: {pnl}\n\n"

    await update.message.reply_text(message, parse_mode="Markdown")


async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    warning, level = generate_news_warning()
    adj = get_confidence_adjustment()

    message = "📅 *ECONOMIC CALENDAR*\n\n"
    message += f"Status: {level}\n"
    message += f"Confidence Adjustment: {adj}%\n\n"
    if level != "CLEAR":
        message += f"{warning}\n\n"

    old_stdout = sys.stdout
    sys.stdout = StringIO()
    display_news_calendar()
    calendar_text = sys.stdout.getvalue()
    sys.stdout = old_stdout
    message += calendar_text

    if len(message) > 4000:
        message = message[:4000] + "..."

    await update.message.reply_text(message, parse_mode="Markdown")


def main():
    if not TELEGRAM_TOKEN:
        print("ERROR: TELEGRAM_TOKEN not found in .env")
        return

    print("Starting Gold Trading Coach Bot...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("trends", trends_command))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CommandHandler("market", market_command))
    app.add_handler(CommandHandler("zones", zones_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("journal", journal_command))
    app.add_handler(CommandHandler("news", news_command))

    print("Bot is running!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()