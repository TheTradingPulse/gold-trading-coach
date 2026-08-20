import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "analysis"))
sys.path.insert(0, str(Path(__file__).parent))

from database import DB_PASSWORD
from trade_engine import get_current_price, get_trends, calculate_alignment, grade_setup
from zone_engine import load_data, detect_supply_zones, detect_demand_zones, is_price_near_zone
from telegram import Bot
import os
from dotenv import load_dotenv

# Load env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def format_alert(direction, entry, stop, target, rr_ratio, grade, alignment, zone_info, tf):
    """Format a trade alert message"""
    emoji = "🟢" if direction == "LONG" else "🔴"

    message = f"""
{emoji} *GOLD TRADE ALERT* {emoji}

*Direction:* {direction}
*Grade:* {grade}
*Timeframe:* {tf}
*Alignment:* {alignment:.0f}%

━━━━━━━━━━━━━━━
*Entry:* ${entry:.2f}
*Stop Loss:* ${stop:.2f}
*Take Profit:* ${target:.2f}
*R:R Ratio:* {rr_ratio}:1
━━━━━━━━━━━━━━━

*Zone:* ${zone_info['lower_bound']:.2f} - ${zone_info['upper_bound']:.2f}
*Zone Strength:* {zone_info['strength']}

⚠️ This is NOT financial advice.
Manage your own risk.
"""
    return message


def format_market_update(trends, direction, alignment):
    """Format a market update message"""
    tf_lines = ""
    for tf in ["M", "W", "D", "4H", "1H", "15m"]:
        t = trends.get(tf, "no_data")
        emoji = "🟢" if t == "bullish" else "🔴" if t == "bearish" else "⚪"
        tf_lines += f"{emoji} {tf}: {t}\n"

    current_price = get_current_price()
    message = f"""
📊 *GOLD MARKET UPDATE*

{tf_lines}
*Alignment:* {direction.upper()} ({alignment:.0f}%)

Current Price: ${current_price:.2f}
"""
    return message


def send_telegram_message(message):
    """Send a message via Telegram"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured. Add TELEGRAM_TOKEN and TELEGRAM_CHAT_ID to .env")
        return False

    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        asyncio.run(bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode="Markdown"
        ))
        print("Alert sent to Telegram!")
        return True
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}")
        return False


def scan_and_alert():
    """Scan for trade opportunities and send alerts"""
    print("\n🔍 Scanning for trade opportunities...")

    current_price = get_current_price()
    if current_price is None:
        print("Could not get current price")
        return

    trends = get_trends()
    direction, alignment = calculate_alignment(trends)

    print(f"Price: ${current_price:.2f}")
    print(f"Alignment: {direction.upper()} ({alignment:.0f}%)")

    if alignment < 60:
        print("Alignment too low. No alerts sent.")
        return

    alerts_sent = 0

    for tf in ["1H", "15m"]:
        df = load_data(tf, limit=300)
        if df is None or len(df) < 10:
            continue

        demand_zones = detect_demand_zones(df)
        supply_zones = detect_supply_zones(df)

        near_demand = [z for z in demand_zones if is_price_near_zone(current_price, z, 0.5)]
        near_supply = [z for z in supply_zones if is_price_near_zone(current_price, z, 0.5)]

        if direction == "bullish" and near_demand:
            for zone in near_demand[-2:]:
                entry = current_price
                stop = zone["lower_bound"] * 0.998
                risk = entry - stop
                target = entry + (risk * 3)
                grade = grade_setup(alignment, zone["strength"])

                message = format_alert("LONG", entry, stop, target, 3.0, grade, alignment, zone, tf)
                send_telegram_message(message)
                alerts_sent += 1

        if direction == "bearish" and near_supply:
            for zone in near_supply[-2:]:
                entry = current_price
                stop = zone["upper_bound"] * 1.002
                risk = stop - entry
                target = entry - (risk * 3)
                grade = grade_setup(alignment, zone["strength"])

                message = format_alert("SHORT", entry, stop, target, 3.0, grade, alignment, zone, tf)
                send_telegram_message(message)
                alerts_sent += 1

    if alerts_sent == 0:
        print("No trade opportunities found near zones.")
    else:
        print(f"Sent {alerts_sent} alert(s) to Telegram.")


def send_market_update():
    """Send a market update to Telegram"""
    trends = get_trends()
    direction, alignment = calculate_alignment(trends)
    message = format_market_update(trends, direction, alignment)
    send_telegram_message(message)


if __name__ == "__main__":
    scan_and_alert()