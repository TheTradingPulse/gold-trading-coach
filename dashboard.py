import streamlit as st
import sys
import pandas as pd
from datetime import datetime

sys.path.insert(0, "core")
sys.path.insert(0, "analysis")

from streamlit_autorefresh import st_autorefresh
from database import get_connection
from zone_engine import load_data, detect_supply_zones, detect_demand_zones, is_price_near_zone
from trade_engine import get_current_price, get_trends, calculate_alignment, grade_setup
from live_data_engine import fetch_latest_data, get_data_source_name
from journal_engine import calculate_statistics, get_all_trades, update_outcome
from dna_engine import log_trade_with_dna
from ai_explainer import generate_explanation
from news_engine import generate_news_warning, get_confidence_adjustment, display_news_calendar
from backtest_engine import run_backtest, get_available_years, get_available_timeframes
from screenshot_engine import load_chart_data
import mplfinance as mpf
import os
from io import StringIO

st.set_page_config(page_title="Gold Trading Coach", page_icon="🥇", layout="wide")

# Auto-refresh every 60 seconds
st_autorefresh(interval=60 * 1000, key="auto_refresh")

# ========== HEADER ==========
st.title("🥇 Gold Trading Coach")
st.caption(f"Data Source: {get_data_source_name()} | Last updated: {datetime.now().strftime('%H:%M:%S')}")

# Current price card
current_price = get_current_price()
if current_price:
    st.markdown(f"## Current Gold Price: **${current_price:.2f}**")

# ========== NAVIGATION BUTTONS ==========
if "page" not in st.session_state:
    st.session_state.page = "📈 Trends"

nav_cols = st.columns(7)
pages = ["📈 Trends", "🗺️ Zones", "📊 Chart", "📈 Stats", "📝 Journal", "🧪 Backtest", "ℹ️ Info"]
for i, page in enumerate(pages):
    if nav_cols[i].button(page, use_container_width=True):
        st.session_state.page = page

st.divider()

# ========== SIDEBAR ==========
with st.sidebar:
    st.header("⚙️ Controls")

    if st.button("🔄 Refresh Data Now", use_container_width=True):
        with st.spinner("Fetching latest GC=F data..."):
            fetch_latest_data()
        st.success("Data refreshed!")
        st.rerun()

    if st.button("📥 Import Full Historical Data", use_container_width=True):
        with st.spinner("Importing full GC=F history..."):
            fetch_latest_data()
        st.success("Full data import started!")
        st.rerun()

    st.caption(f"Source: {get_data_source_name()}")

    st.divider()

    st.subheader("📈 News")
    try:
        warning, level = generate_news_warning()
        if level == "HIGH":
            st.error(warning)
        elif level == "MEDIUM":
            st.warning(warning)
        else:
            st.success("No major news events")
    except Exception:
        pass

    st.divider()

    st.subheader("📊 Quick Stats")
    try:
        stats = calculate_statistics()
        if stats:
            st.metric("Trades", stats["total_trades"])
            st.metric("Win Rate", f"{stats['win_rate']}%")
            st.metric("Profit Factor", f"{stats['profit_factor']}")
    except Exception:
        pass

# ========== PAGE CONTENT ==========
page = st.session_state.page

# ========== TRENDS PAGE ==========
if page == "📈 Trends":
    st.subheader("Multi-Timeframe Trend Analysis")

    try:
        trends = get_trends()
        direction, alignment = calculate_alignment(trends)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Direction", direction.upper())
        c2.metric("Alignment", f"{alignment:.0f}%")
        c3.metric("Price", f"${current_price:.2f}" if current_price else "N/A")
        c4.metric("News Adj", f"{get_confidence_adjustment()}%")

        st.divider()

        tf_order = ["M", "W", "D", "4H", "1H", "15m"]
        tf_cols = st.columns(len(tf_order))
        for i, tf in enumerate(tf_order):
            trend = trends.get(tf, "no_data")
            emoji = "🟢" if trend == "bullish" else "🔴" if trend == "bearish" else "⚪"
            tf_cols[i].markdown(f"**{tf}** {emoji}")

        if alignment < 60:
            st.warning(f"Alignment {alignment:.0f}% is below 60%. No trades recommended.")
        else:
            st.subheader("🔍 Trade Opportunity")

            if current_price:
                df_scan = load_data("1H", limit=300)
                if df_scan is not None and len(df_scan) >= 10:
                    demand = detect_demand_zones(df_scan)
                    supply = detect_supply_zones(df_scan)
                    near_demand = [z for z in demand if is_price_near_zone(current_price, z, 0.5)]
                    near_supply = [z for z in supply if is_price_near_zone(current_price, z, 0.5)]

                    if direction == "bullish" and near_demand:
                        zone = near_demand[-1]
                        entry = current_price
                        stop = zone["lower_bound"] * 0.998
                        risk = entry - stop
                        target = entry + (risk * 3)
                        grade = grade_setup(alignment, zone["strength"])

                        st.success(f"**LONG Signal** | Grade: {grade}")
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Entry", f"${entry:.2f}")
                        c2.metric("Stop", f"${stop:.2f}")
                        c3.metric("Target", f"${target:.2f}")
                        c4.metric("R:R", "3:1")

                        if st.button("📝 Log this LONG trade"):
                            tid, tags = log_trade_with_dna("LONG", entry, stop, target, 3.0, grade, alignment, "demand", "1H")
                            st.success(f"Trade #{tid} logged with tags: {', '.join(tags)}")

                        with st.expander("📝 AI Explanation"):
                            st.markdown(generate_explanation("LONG", entry, stop, target, zone, "1H", grade, alignment))

                    elif direction == "bearish" and near_supply:
                        zone = near_supply[-1]
                        entry = current_price
                        stop = zone["upper_bound"] * 1.002
                        risk = stop - entry
                        target = entry - (risk * 3)
                        grade = grade_setup(alignment, zone["strength"])

                        st.error(f"**SHORT Signal** | Grade: {grade}")
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Entry", f"${entry:.2f}")
                        c2.metric("Stop", f"${stop:.2f}")
                        c3.metric("Target", f"${target:.2f}")
                        c4.metric("R:R", "3:1")

                        if st.button("📝 Log this SHORT trade"):
                            tid, tags = log_trade_with_dna("SHORT", entry, stop, target, 3.0, grade, alignment, "supply", "1H")
                            st.success(f"Trade #{tid} logged with tags: {', '.join(tags)}")

                        with st.expander("📝 AI Explanation"):
                            st.markdown(generate_explanation("SHORT", entry, stop, target, zone, "1H", grade, alignment))
                    else:
                        st.info("No trade opportunity right now. Price not at a valid zone.")
    except Exception as e:
        st.error(f"Error loading trends: {e}")

# ========== ZONES PAGE ==========
elif page == "🗺️ Zones":
    st.subheader("Active Supply & Demand Zones (1H)")

    try:
        df_zone = load_data("1H", limit=300)
        if df_zone is not None and len(df_zone) >= 10:
            price = df_zone["close"].iloc[-1]
            supply = detect_supply_zones(df_zone)
            demand = detect_demand_zones(df_zone)
            near_supply = [z for z in supply if is_price_near_zone(price, z, 1.0)]
            near_demand = [z for z in demand if is_price_near_zone(price, z, 1.0)]

            c1, c2, c3 = st.columns(3)
            c1.metric("Current Price", f"${price:.2f}")
            c2.metric("Supply Zones", len(supply))
            c3.metric("Demand Zones", len(demand))

            st.divider()

            z1, z2 = st.columns(2)
            with z1:
                st.markdown("### 🔴 Supply Zones")
                if near_supply:
                    for z in near_supply[-5:]:
                        st.warning(f"${z['lower_bound']:.2f} - ${z['upper_bound']:.2f} (S:{z['strength']})")
                else:
                    st.write("No active supply zones near price")
                st.caption("Recent zones:")
                for z in supply[-5:]:
                    st.write(f"• ${z['lower_bound']:.2f} - ${z['upper_bound']:.2f} (S:{z['strength']})")
            with z2:
                st.markdown("### 🟢 Demand Zones")
                if near_demand:
                    for z in near_demand[-5:]:
                        st.success(f"${z['lower_bound']:.2f} - ${z['upper_bound']:.2f} (S:{z['strength']})")
                else:
                    st.write("No active demand zones near price")
                st.caption("Recent zones:")
                for z in demand[-5:]:
                    st.write(f"• ${z['lower_bound']:.2f} - ${z['upper_bound']:.2f} (S:{z['strength']})")
        else:
            st.warning("Not enough data for zones. Please refresh data.")
    except Exception as e:
        st.error(f"Error loading zones: {e}")

# ========== CHART PAGE ==========
elif page == "📊 Chart":
    st.subheader("Gold Futures Chart (1H)")

    try:
        df_chart = load_chart_data("1H", limit=200)
        if df_chart is not None and len(df_chart) >= 5:
            sma_20 = df_chart["Close"].rolling(window=20).mean()
            sma_50 = df_chart["Close"].rolling(window=50).mean()

            mc = mpf.make_marketcolors(up='green', down='red', edge='inherit', wick='inherit', volume='in')
            s = mpf.make_mpf_style(marketcolors=mc, gridstyle=':', base_mpf_style='charles')
            apds = [
                mpf.make_addplot(sma_20, color='blue', width=0.8),
                mpf.make_addplot(sma_50, color='orange', width=0.8)
            ]

            temp_file = "temp_chart.png"
            mpf.plot(df_chart, type='candle', style=s, title='Gold Futures (GC=F) - 1H',
                     ylabel='Price ($)', volume=True, addplot=apds, figsize=(14, 7), savefig=temp_file)
            st.image(temp_file, use_container_width=True)
            if os.path.exists(temp_file):
                os.remove(temp_file)
        else:
            st.warning("Not enough chart data. Refresh data first.")
    except Exception as e:
        st.error(f"Chart error: {e}")

# ========== STATS PAGE ==========
elif page == "📈 Stats":
    st.subheader("Performance Statistics")

    try:
        stats = calculate_statistics()
        if stats:
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Trades", stats["total_trades"])
            c2.metric("Win Rate", f"{stats['win_rate']}%")
            c3.metric("Profit Factor", f"{stats['profit_factor']}")
            c4.metric("Expectancy", f"${stats['expectancy']:.2f}")
            c5.metric("Total P&L", f"${stats['total_pnl']:.2f}")

            st.divider()

            d1, d2, d3 = st.columns(3)
            d1.write(f"Wins: {stats['wins']}\nLosses: {stats['losses']}\nBreakeven: {stats['breakeven']}")
            d2.write(f"Avg Win: ${stats['avg_win']:.2f}\nAvg Loss: ${stats['avg_loss']:.2f}")
            d3.write(f"Max Drawdown: ${stats['max_drawdown']:.2f}\nProfit Factor: {stats['profit_factor']}")

            st.divider()

            from dna_engine import analyze_dna_performance
            dna_df = analyze_dna_performance()
            if len(dna_df) > 0:
                st.subheader("🧬 Trade DNA Analysis")
                st.dataframe(dna_df, use_container_width=True)
        else:
            st.info("No closed trades yet. Statistics will appear after trades complete.")
    except Exception as e:
        st.error(f"Error loading statistics: {e}")

# ========== JOURNAL PAGE ==========
elif page == "📝 Journal":
    st.subheader("Trade Journal")

    try:
        trades_df = get_all_trades()
        if len(trades_df) > 0:
            for _, trade in trades_df.head(20).iterrows():
                outcome = str(trade["outcome"])
                emoji = "🟢" if outcome == "WIN" else "🔴" if outcome == "LOSS" else "⚪" if outcome == "BREAKEVEN" else "🟡"
                with st.expander(f"{emoji} #{trade['id']}: {trade['direction']} @ ${float(trade['entry']):.2f} | Grade: {trade['grade']} | {outcome}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.write(f"Entry: ${float(trade['entry']):.2f}")
                        st.write(f"Stop: ${float(trade['stop']):.2f}")
                        st.write(f"Target: ${float(trade['target']):.2f}")
                    with c2:
                        st.write(f"Outcome: {outcome}")
                        if trade['exit_price'] and str(trade['exit_price']) != 'nan':
                            st.write(f"Exit: ${float(trade['exit_price']):.2f}")
                        if trade['pnl'] and str(trade['pnl']) != 'nan':
                            st.write(f"P&L: ${float(trade['pnl']):.2f}")

                    if outcome == "OPEN":
                        new_outcome = st.selectbox("Update Outcome", ["OPEN", "WIN", "LOSS", "BREAKEVEN"], key=f"o_{trade['id']}")
                        ep = st.number_input("Exit Price", value=float(trade['entry']), key=f"e_{trade['id']}")
                        if st.button(f"Update #{trade['id']}", key=f"u_{trade['id']}"):
                            if new_outcome != "OPEN":
                                update_outcome(trade['id'], new_outcome, ep)
                                st.rerun()
        else:
            st.info("No trades in journal yet.")
    except Exception as e:
        st.error(f"Error loading journal: {e}")

# ========== BACKTEST PAGE ==========
elif page == "🧪 Backtest":
    st.subheader("Historical Backtest")

    try:
        available_years = get_available_years()

        if available_years:
            st.success(f"Data available from {available_years[0]} to {available_years[-1]}")

            col1, col2, col3 = st.columns(3)
            with col1:
                selected_year = st.selectbox("Year", ["All"] + [str(y) for y in available_years], key="bt_year")
                if selected_year != "All":
                    start_date = f"{selected_year}-01-01"
                    end_date = f"{selected_year}-12-31"
                else:
                    start_date = f"{available_years[0]}-01-01"
                    end_date = f"{available_years[-1]}-12-31"
            with col2:
                min_strength = st.slider("Min Zone Strength", 5, 80, 15, key="bt_str")
            with col3:
                bt_trail = st.checkbox("Use Trailing Stop", value=False, key="bt_trail")

            if st.button("🚀 Run Backtest", type="primary", use_container_width=True):
                with st.spinner("Running backtest..."):
                    result = run_backtest(
                        start_date=start_date,
                        end_date=end_date,
                        initial_capital=10000,
                        risk_per_trade=0.02,
                        zone_timeframe="D",
                        entry_timeframe="D",
                        trend_timeframe="D",
                        min_zone_strength=min_strength,
                        trend_mode="OR",
                        use_trailing_stop=bt_trail,
                    )
                    if result and result["stats"]["total_trades"] > 0:
                        s = result["stats"]
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Trades", s["total_trades"])
                        c2.metric("Win Rate", f"{s['win_rate']:.1f}%")
                        c3.metric("Profit Factor", f"{s['profit_factor']:.2f}")
                        c4.metric("Return", f"{s['total_return']:.1f}%")
                        st.write(f"Final capital: ${s['final_capital']:,.0f} | Max DD: {s['max_drawdown']:.1f}%")
                    else:
                        st.warning("No trades generated. Try lower zone strength or All years.")
        else:
            st.warning("No historical data. Please import data first.")
    except Exception as e:
        st.error(f"Backtest error: {e}")

# ========== INFO PAGE ==========
elif page == "ℹ️ Info":
    st.subheader("System Information")

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT timeframe, COUNT(*) FROM gold_ohlcv GROUP BY timeframe ORDER BY timeframe")
        rows = cur.fetchall()
        if rows:
            st.write("**Database Status**")
            st.dataframe(pd.DataFrame(rows, columns=["Timeframe", "Row Count"]), use_container_width=True)

        cur.execute("SELECT timeframe, MAX(timestamp) FROM gold_ohlcv GROUP BY timeframe ORDER BY timeframe")
        latest = cur.fetchall()
        if latest:
            st.write("**Latest Data Timestamps**")
            st.dataframe(pd.DataFrame(latest, columns=["Timeframe", "Latest Timestamp"]), use_container_width=True)

        cur.close()
        conn.close()
    except Exception as e:
        st.error(f"Database error: {e}")

    st.divider()
    st.write("**Upcoming Economic Events**")
    try:
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        display_news_calendar()
        st.text(sys.stdout.getvalue())
        sys.stdout = old_stdout
    except Exception:
        pass

    st.divider()
    st.write(f"**Data Source:** {get_data_source_name()}")
    st.write("**Symbol:** GC=F (continuous front-month COMEX Gold futures)")
    st.write("**Platform:** Railway")
    st.warning("⚠️ NOT financial advice. Trader responsible for all risk management.")

st.caption("⚠️ Not financial advice. Always manage your own risk.")