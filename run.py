import streamlit as st
import sys
sys.path.insert(0, "core")
sys.path.insert(0, "analysis")

import pandas as pd
from database import DB_PASSWORD
import psycopg2
from trend_engine import assess_trend
from zone_engine import load_data, detect_supply_zones, detect_demand_zones, is_price_near_zone
from trade_engine import get_current_price, get_trends, calculate_alignment, grade_setup
from journal_engine import get_all_trades, calculate_statistics, log_trade, update_outcome, display_statistics
from screenshot_engine import load_chart_data
from ai_explainer import generate_explanation
from news_engine import generate_news_warning, get_confidence_adjustment, get_event_tags, display_news_calendar
import mplfinance as mpf
from datetime import datetime
import os

# Page config
st.set_page_config(
    page_title="Gold Trading Coach",
    page_icon="🥇",
    layout="wide"
)

st.title("🥇 Gold Trading Coach")
st.caption("Gold Futures (GC) - Decision Support System | NOT Financial Advice")

# ============================================
# SIDEBAR
# ============================================
st.sidebar.header("⚙️ Controls")

zone_tf = st.sidebar.selectbox(
    "Zone Analysis Timeframe",
    ["1m", "5m", "15m", "1H", "4H", "D", "W", "M"],
    index=3
)

scan_tf = st.sidebar.selectbox(
    "Trade Scan Timeframe",
    ["1H", "15m", "5m", "4H"],
    index=0
)

chart_tf = st.sidebar.selectbox(
    "Chart Timeframe",
    ["1m", "5m", "15m", "1H", "4H", "D"],
    index=3
)

alignment_threshold = st.sidebar.slider(
    "Alignment Threshold %",
    min_value=40, max_value=100, value=60, step=5
)

tolerance = st.sidebar.slider(
    "Zone Proximity %",
    min_value=0.2, max_value=2.0, value=0.5, step=0.1
)

st.sidebar.divider()

col_a, col_b = st.sidebar.columns(2)
with col_a:
    refresh_btn = st.button("🔄 Refresh")
with col_b:
    fetch_btn = st.button("📊 Fetch Data")

if fetch_btn:
    from data_engine import fetch_and_store
    with st.spinner("Fetching latest market data..."):
        fetch_and_store("1H", "5d")
        fetch_and_store("15m", "5d")
        fetch_and_store("5m", "5d")
        fetch_and_store("1m", "2d")
    st.sidebar.success("✅ Data updated!")

st.sidebar.divider()

# Quick stats
st.sidebar.subheader("📈 Quick Stats")
stats = calculate_statistics()
if stats:
    st.sidebar.metric("Total Trades", stats["total_trades"])
    st.sidebar.metric("Win Rate", f"{stats['win_rate']}%")
    st.sidebar.metric("Profit Factor", f"{stats['profit_factor']}")
    st.sidebar.metric("Total P&L", f"${stats['total_pnl']:.2f}")

st.sidebar.divider()

# News warning
warning, level = generate_news_warning()
if level == "HIGH":
    st.sidebar.error(warning)
elif level == "MEDIUM":
    st.sidebar.warning(warning)
else:
    st.sidebar.success("No major news events")

# ============================================
# MAIN CONTENT
# ============================================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📈 Trends & Signals",
    "🗺️ Supply & Demand",
    "📊 Charts",
    "📈 Statistics",
    "📝 Trade Journal",
    "ℹ️ System Info"
])

# ============================================
# TAB 1: TRENDS & SIGNALS
# ============================================
with tab1:
    st.subheader("Multi-Timeframe Trend Analysis")
    
    trends = get_trends()
    direction, alignment = calculate_alignment(trends)
    
    tf_order = ["M", "W", "D", "4H", "1H", "15m", "5m", "1m"]
    cols = st.columns(len(tf_order))
    
    for i, tf in enumerate(tf_order):
        trend = trends.get(tf, "no_data")
        color = "🟢" if trend == "bullish" else "🔴" if trend == "bearish" else "⚪"
        cols[i].metric(label=tf, value=color)
    
    st.divider()
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Overall Direction", direction.upper())
    with c2:
        st.metric("Alignment Score", f"{alignment:.0f}%",
                  delta="Tradeable" if alignment >= alignment_threshold else "Wait")
    with c3:
        current_price = get_current_price()
        if current_price:
            st.metric("Current Price", f"${current_price:.2f}")
    with c4:
        adj = get_confidence_adjustment()
        st.metric("News Confidence Adj", f"{adj}%")
    
    if alignment < alignment_threshold:
        st.warning(f"⚠️ Alignment ({alignment:.0f}%) below threshold ({alignment_threshold}%). No trades recommended.")
    
    st.divider()
    st.subheader("🔍 Trade Opportunities")
    
    if alignment >= alignment_threshold:
        current_price = get_current_price()
        
        if current_price:
            df_tf = load_data(scan_tf, limit=300)
            
            if df_tf is not None and len(df_tf) >= 10:
                demand_zones = detect_demand_zones(df_tf)
                supply_zones = detect_supply_zones(df_tf)
                
                price = df_tf["close"].iloc[-1]
                near_demand = [z for z in demand_zones if is_price_near_zone(price, z, tolerance)]
                near_supply = [z for z in supply_zones if is_price_near_zone(price, z, tolerance)]
                
                # Store trade info in session state for logging
                if "current_trade" not in st.session_state:
                    st.session_state.current_trade = None
                
                signal_count = 0
                
                if direction == "bullish" and near_demand:
                    for zone in near_demand[-2:]:
                        entry = price
                        stop = zone["lower_bound"] * 0.998
                        risk = entry - stop
                        target_3r = entry + (risk * 3)
                        target_4r = entry + (risk * 4)
                        trade_grade = grade_setup(alignment, zone["strength"])
                        
                        signal_count += 1
                        with st.container():
                            st.success(f"**LONG #{signal_count}** | Grade: {trade_grade} | {scan_tf}")
                            c1, c2, c3, c4, c5 = st.columns(5)
                            c1.metric("Entry", f"${entry:.2f}")
                            c2.metric("Stop", f"${stop:.2f}")
                            c3.metric("Target (3:1)", f"${target_3r:.2f}")
                            c4.metric("Target (4:1)", f"${target_4r:.2f}")
                            c5.metric("R:R", "3:1")
                            
                            # Log trade button
                            if st.button(f"📝 Log This Trade (LONG #{signal_count})", key=f"log_long_{signal_count}"):
                                trade_id = log_trade(
                                    direction="LONG",
                                    entry=entry,
                                    stop=stop,
                                    target=target_3r,
                                    rr_ratio=3.0,
                                    grade=trade_grade,
                                    alignment_score=alignment,
                                    zone_type="demand",
                                    notes=f"Auto-logged from {scan_tf} signal"
                                )
                                st.success(f"Trade #{trade_id} logged! Track it in Trade Journal tab.")
                                st.session_state.current_trade = trade_id
                            
                            # Show explanation
                            with st.expander("📝 AI Explanation"):
                                explanation = generate_explanation(
                                    direction="LONG", entry=entry, stop=stop,
                                    target=target_3r, zone_info=zone, tf=scan_tf,
                                    grade=trade_grade, alignment=alignment
                                )
                                st.markdown(explanation)
                            
                            st.divider()
                
                if direction == "bearish" and near_supply:
                    for zone in near_supply[-2:]:
                        entry = price
                        stop = zone["upper_bound"] * 1.002
                        risk = stop - entry
                        target_3r = entry - (risk * 3)
                        target_4r = entry - (risk * 4)
                        trade_grade = grade_setup(alignment, zone["strength"])
                        
                        signal_count += 1
                        with st.container():
                            st.error(f"**SHORT #{signal_count}** | Grade: {trade_grade} | {scan_tf}")
                            c1, c2, c3, c4, c5 = st.columns(5)
                            c1.metric("Entry", f"${entry:.2f}")
                            c2.metric("Stop", f"${stop:.2f}")
                            c3.metric("Target (3:1)", f"${target_3r:.2f}")
                            c4.metric("Target (4:1)", f"${target_4r:.2f}")
                            c5.metric("R:R", "3:1")
                            
                            if st.button(f"📝 Log This Trade (SHORT #{signal_count})", key=f"log_short_{signal_count}"):
                                trade_id = log_trade(
                                    direction="SHORT",
                                    entry=entry,
                                    stop=stop,
                                    target=target_3r,
                                    rr_ratio=3.0,
                                    grade=trade_grade,
                                    alignment_score=alignment,
                                    zone_type="supply",
                                    notes=f"Auto-logged from {scan_tf} signal"
                                )
                                st.success(f"Trade #{trade_id} logged!")
                            
                            with st.expander("📝 AI Explanation"):
                                explanation = generate_explanation(
                                    direction="SHORT", entry=entry, stop=stop,
                                    target=target_3r, zone_info=zone, tf=scan_tf,
                                    grade=trade_grade, alignment=alignment
                                )
                                st.markdown(explanation)
                            
                            st.divider()
                
                if signal_count == 0:
                    st.info("No zones near current price. Waiting for pullback.")
    else:
        st.info(f"Waiting for alignment to reach {alignment_threshold}%...")

# ============================================
# TAB 2: SUPPLY & DEMAND ZONES
# ============================================
with tab2:
    st.subheader(f"🗺️ Supply & Demand Zones - {zone_tf}")
    
    df_zone = load_data(zone_tf, limit=500)
    
    if df_zone is not None and len(df_zone) >= 10:
        current_price = df_zone["close"].iloc[-1]
        supply_all = detect_supply_zones(df_zone)
        demand_all = detect_demand_zones(df_zone)
        
        near_supply = [z for z in supply_all if is_price_near_zone(current_price, z, tolerance)]
        near_demand = [z for z in demand_all if is_price_near_zone(current_price, z, tolerance)]
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Current Price", f"${current_price:.2f}")
        c2.metric("Supply Zones", len(supply_all))
        c3.metric("Demand Zones", len(demand_all))
        c4.metric("Active Near Price", len(near_supply) + len(near_demand))
        
        st.divider()
        
        z1, z2 = st.columns(2)
        
        with z1:
            st.subheader("🔴 Supply Zones")
            if near_supply:
                st.caption("Active (price near):")
                for z in near_supply[-5:]:
                    st.warning(f"**${z['lower_bound']:.2f} - ${z['upper_bound']:.2f}** | S:{z['strength']}")
            st.caption("All detected:")
            for z in supply_all[-10:]:
                st.write(f"• ${z['lower_bound']:.2f} - ${z['upper_bound']:.2f} | S:{z['strength']}")
        
        with z2:
            st.subheader("🟢 Demand Zones")
            if near_demand:
                st.caption("Active (price near):")
                for z in near_demand[-5:]:
                    st.success(f"**${z['lower_bound']:.2f} - ${z['upper_bound']:.2f}** | S:{z['strength']}")
            st.caption("All detected:")
            for z in demand_all[-10:]:
                st.write(f"• ${z['lower_bound']:.2f} - ${z['upper_bound']:.2f} | S:{z['strength']}")

# ============================================
# TAB 3: CHARTS
# ============================================
with tab3:
    st.subheader(f"📊 Candlestick Chart - {chart_tf}")
    
    df_chart = load_chart_data(chart_tf, limit=100)
    
    if df_chart is not None and len(df_chart) >= 5:
        # Add SMAs
        sma_20 = df_chart["Close"].rolling(window=20).mean()
        sma_50 = df_chart["Close"].rolling(window=50).mean()
        
        mc = mpf.make_marketcolors(up='green', down='red', edge='inherit', wick='inherit', volume='in')
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle=':', base_mpf_style='charles')
        
        apds = [
            mpf.make_addplot(sma_20, color='blue', width=0.7, label='SMA 20'),
            mpf.make_addplot(sma_50, color='orange', width=0.7, label='SMA 50')
        ]
        
        fig, axes = mpf.plot(
            df_chart,
            type='candle',
            style=s,
            title=f'Gold Futures (GC) - {chart_tf}',
            ylabel='Price ($)',
            volume=True,
            addplot=apds,
            returnfig=True,
            figsize=(12, 7)
        )
        
        st.pyplot(fig)
        
        # Price stats
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Open", f"${df_chart['Open'].iloc[-1]:.2f}")
        c2.metric("High", f"${df_chart['High'].iloc[-1]:.2f}")
        c3.metric("Low", f"${df_chart['Low'].iloc[-1]:.2f}")
        c4.metric("Close", f"${df_chart['Close'].iloc[-1]:.2f}")
    else:
        st.warning(f"Not enough data for {chart_tf}")

# ============================================
# TAB 4: STATISTICS
# ============================================
with tab4:
    st.subheader("📈 Performance Statistics")
    
    stats = calculate_statistics()
    
    if stats:
        kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
        kpi1.metric("Total Trades", stats["total_trades"])
        kpi2.metric("Win Rate", f"{stats['win_rate']}%")
        kpi3.metric("Profit Factor", f"{stats['profit_factor']}")
        kpi4.metric("Expectancy", f"${stats['expectancy']:.2f}")
        kpi5.metric("Total P&L", f"${stats['total_pnl']:.2f}")
        
        st.divider()
        
        d1, d2, d3 = st.columns(3)
        with d1:
            st.write("**Trade Breakdown**")
            st.write(f"Wins: {stats['wins']}")
            st.write(f"Losses: {stats['losses']}")
            st.write(f"Breakeven: {stats['breakeven']}")
            st.write(f"Win Rate: {stats['win_rate']}%")
        with d2:
            st.write("**Profit Metrics**")
            st.write(f"Avg Win: ${stats['avg_win']:.2f}")
            st.write(f"Avg Loss: ${stats['avg_loss']:.2f}")
            st.write(f"Profit Factor: {stats['profit_factor']}")
            st.write(f"Expectancy: ${stats['expectancy']:.2f}")
        with d3:
            st.write("**Risk Metrics**")
            st.write(f"Max Drawdown: ${stats['max_drawdown']:.2f}")
            st.write(f"Total P&L: ${stats['total_pnl']:.2f}")
        
        st.divider()
        st.subheader("KPI Assessment")
        tc1, tc2, tc3 = st.columns(3)
        with tc1:
            if stats['total_trades'] >= 10:
                st.success("✅ 10+ trades")
            else:
                st.warning("⚠️ <10 trades")
        with tc2:
            if stats['win_rate'] >= 40:
                st.success(f"✅ Win Rate {stats['win_rate']}%")
            else:
                st.error(f"❌ Win Rate {stats['win_rate']}%")
        with tc3:
            if stats['profit_factor'] >= 1.5:
                st.success(f"✅ Profit Factor {stats['profit_factor']}")
            else:
                st.error(f"❌ Profit Factor {stats['profit_factor']}")
    else:
        st.info("No closed trades yet.")

# ============================================
# TAB 5: TRADE JOURNAL
# ============================================
with tab5:
    st.subheader("📝 Trade Journal")
    
    filter_cols = st.columns(4)
    with filter_cols[0]:
        outcome_filter = st.selectbox("Outcome", ["ALL", "OPEN", "WIN", "LOSS", "BREAKEVEN"])
    with filter_cols[1]:
        grade_filter = st.selectbox("Grade", ["ALL", "A+", "A", "B", "C", "Avoid"])
    with filter_cols[2]:
        direction_filter = st.selectbox("Direction", ["ALL", "LONG", "SHORT"])
    
    trades_df = get_all_trades()
    
    if len(trades_df) > 0:
        filtered = trades_df.copy()
        if outcome_filter != "ALL":
            filtered = filtered[filtered["outcome"] == outcome_filter]
        if grade_filter != "ALL":
            filtered = filtered[filtered["grade"] == grade_filter]
        if direction_filter != "ALL":
            filtered = filtered[filtered["direction"] == direction_filter]
        
        st.write(f"Showing {len(filtered)} of {len(trades_df)} trades")
        
        for _, trade in filtered.iterrows():
            outcome = trade["outcome"]
            emoji = "🟢" if outcome == "WIN" else "🔴" if outcome == "LOSS" else "⚪" if outcome == "BREAKEVEN" else "🟡"
            
            with st.expander(f"{emoji} #{trade['id']}: {trade['direction']} @ ${trade['entry']:.2f} | Grade: {trade['grade']} | {outcome}"):
                c1, c2 = st.columns(2)
                with c1:
                    st.write(f"**Entry:** ${trade['entry']:.2f}")
                    st.write(f"**Stop:** ${trade['stop']:.2f}")
                    st.write(f"**Target:** ${trade['target']:.2f}")
                    st.write(f"**Direction:** {trade['direction']}")
                with c2:
                    st.write(f"**Outcome:** {trade['outcome']}")
                    if trade['exit_price']:
                        st.write(f"**Exit:** ${trade['exit_price']:.2f}")
                    if trade['pnl']:
                        st.write(f"**P&L:** ${trade['pnl']:.2f}")
                    st.write(f"**R:R:** {trade['rr_ratio']}:1")
                
                # Update outcome
                if outcome == "OPEN":
                    new_outcome = st.selectbox(
                        "Update Outcome",
                        ["OPEN", "WIN", "LOSS", "BREAKEVEN"],
                        key=f"outcome_{trade['id']}"
                    )
                    exit_price = st.number_input(
                        "Exit Price",
                        value=float(trade['entry']),
                        step=0.1,
                        key=f"exit_{trade['id']}"
                    )
                    if st.button(f"Update Trade #{trade['id']}", key=f"update_{trade['id']}"):
                        if new_outcome != "OPEN":
                            update_outcome(trade['id'], new_outcome, exit_price)
                            st.rerun()
    else:
        st.info("No trades in journal yet.")

# ============================================
# TAB 6: SYSTEM INFO
# ============================================
with tab6:
    st.subheader("ℹ️ System Information")
    
    conn = psycopg2.connect(
        host="localhost", port="5432", database="gold_trading",
        user="postgres", password=DB_PASSWORD
    )
    cur = conn.cursor()
    
    st.write("**Database Status**")
    cur.execute("SELECT timeframe, COUNT(*) as count FROM gold_ohlcv GROUP BY timeframe ORDER BY timeframe")
    rows = cur.fetchall()
    db_df = pd.DataFrame(rows, columns=["Timeframe", "Row Count"])
    st.dataframe(db_df, use_container_width=True)
    
    st.write("**Latest Data**")
    cur.execute("SELECT timeframe, MAX(timestamp) FROM gold_ohlcv GROUP BY timeframe ORDER BY timeframe")
    latest = cur.fetchall()
    latest_df = pd.DataFrame(latest, columns=["Timeframe", "Latest Timestamp"])
    st.dataframe(latest_df, use_container_width=True)
    
    cur.close()
    conn.close()
    
    st.divider()
    
    # News calendar
    st.write("**Upcoming Economic Events**")
    
    # Collect events for display
    import sys
    from io import StringIO
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    display_news_calendar()
    output = sys.stdout.getvalue()
    sys.stdout = old_stdout
    
    st.text(output)
    
    st.divider()
    st.write("**Project Details**")
    st.write("- Symbol: Gold Futures (GC)")
    st.write("- Version: 1.0")
    st.write("- Data Source: Yahoo Finance")
    st.write("- Database: PostgreSQL (local)")
    st.write("- Dashboard: Streamlit")
    st.warning("⚠️ NOT financial advice. Trader responsible for all risk management.")

# Footer
st.divider()
st.caption(f"Gold Trading Coach V1 | Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")