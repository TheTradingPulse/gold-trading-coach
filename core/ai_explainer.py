import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "analysis"))
sys.path.insert(0, str(Path(__file__).parent))

from trade_engine import get_current_price, get_trends, calculate_alignment, grade_setup
from zone_engine import load_data, detect_supply_zones, detect_demand_zones, is_price_near_zone
from datetime import datetime


def generate_explanation(direction, entry, stop, target, zone_info, tf, grade, alignment):
    """Generate an AI-style explanation for a trade setup"""

    current_price = get_current_price()
    trends = get_trends()
    trend_direction, _ = calculate_alignment(trends)

    # Trend context
    m_trend = trends.get("M", "neutral")
    w_trend = trends.get("W", "neutral")
    d_trend = trends.get("D", "neutral")
    h4_trend = trends.get("4H", "neutral")
    h1_trend = trends.get("1H", "neutral")

    zone_type = "demand" if direction == "LONG" else "supply"
    zone_label = "support" if direction == "LONG" else "resistance"

    # Build explanation
    explanation = f"""
📝 *TRADE EXPLANATION*

*What is happening?*
Gold is showing a {trend_direction} bias with {alignment:.0f}% multi-timeframe alignment. 
Price is currently at ${current_price:.2f}, interacting with a key {zone_label} zone on the {tf} timeframe.

*Why is it happening?*
"""
    if direction == "LONG":
        explanation += f"""The broader trend structure shows monthly ({m_trend}), weekly ({w_trend}), 
and daily ({d_trend}) trends supporting upside movement. 
Price has pulled back into a demand zone where buyers previously entered aggressively.
"""
    else:
        explanation += f"""The broader trend structure shows monthly ({m_trend}), weekly ({w_trend}), 
and daily ({d_trend}) trends supporting downside movement. 
Price has rallied into a supply zone where sellers previously entered aggressively.
"""

    explanation += f"""
*Why this zone matters?*
This {zone_type} zone (${zone_info['lower_bound']:.2f} - ${zone_info['upper_bound']:.2f}) 
formed on {zone_info['created_at'][:16]} with a strength rating of {zone_info['strength']}/100.
Zones represent areas where institutional traders previously placed large orders,
making them high-probability reversal points.

*Why the trade exists?*
"""
    if direction == "LONG":
        explanation += f"""Entry at ${entry:.2f} places you at the zone with a tight stop 
at ${stop:.2f} (below the zone low). Target at ${target:.2f} offers a 
3:1 reward-to-risk ratio, meaning you only need a 40% win rate to be profitable.
"""
    else:
        explanation += f"""Entry at ${entry:.2f} places you at the zone with a tight stop 
at ${stop:.2f} (above the zone high). Target at ${target:.2f} offers a 
3:1 reward-to-risk ratio, meaning you only need a 40% win rate to be profitable.
"""

    explanation += f"""
*What invalidates the trade?*
- Price closes beyond the stop loss level
- Alignment drops below 60%
- Major news event causes unexpected volatility
- Zone breaks with strong momentum

*What should you learn?*
This is a {grade}-grade setup with {alignment:.0f}% alignment.
Higher-grade setups (A+, A) perform better over time.
Track every outcome in your journal to build your own edge.

⚠️ *This is NOT financial advice. Manage your own risk.*
"""
    return explanation


def generate_market_summary():
    """Generate a market overview explanation"""
    trends = get_trends()
    direction, alignment = calculate_alignment(trends)
    current_price = get_current_price()

    summary = f"""
📊 *GOLD MARKET SUMMARY*
{datetime.now().strftime('%Y-%m-%d %H:%M')}

*Current Price:* ${current_price:.2f}
*Market Bias:* {direction.upper()}
*Alignment:* {alignment:.0f}%

*Multi-Timeframe View:*
"""
    for tf in ["M", "W", "D", "4H", "1H", "15m", "5m"]:
        t = trends.get(tf, "no_data")
        emoji = "🟢" if t == "bullish" else "🔴" if t == "bearish" else "⚪"
        summary += f"{emoji} {tf}: {t}\n"

    if alignment >= 80:
        summary += "\n*Assessment:* Strong alignment. High-confidence setups possible."
    elif alignment >= 60:
        summary += "\n*Assessment:* Moderate alignment. Be selective with entries."
    else:
        summary += "\n*Assessment:* Low alignment. Best to wait or trade with caution."

    return summary


if __name__ == "__main__":
    # Test: Generate explanation for a sample setup
    current_price = get_current_price()
    trends = get_trends()
    direction, alignment = calculate_alignment(trends)

    print("=== Market Summary ===")
    print(generate_market_summary())

    if alignment >= 60 and current_price:
        df = load_data("1H", limit=300)
        demand_zones = detect_demand_zones(df)
        near_demand = [z for z in demand_zones if is_price_near_zone(current_price, z, 0.5)]

        if direction == "bullish" and near_demand:
            zone = near_demand[-1]
            entry = current_price
            stop = zone["lower_bound"] * 0.998
            risk = entry - stop
            target = entry + (risk * 3)
            grade = grade_setup(alignment, zone["strength"])

            print("\n=== Sample Trade Explanation ===")
            explanation = generate_explanation(
                direction="LONG",
                entry=entry,
                stop=stop,
                target=target,
                zone_info=zone,
                tf="1H",
                grade=grade,
                alignment=alignment
            )
            print(explanation)