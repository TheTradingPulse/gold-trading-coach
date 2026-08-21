import sys
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import altair as alt
import streamlit as st

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'core'))
from market_clock import replay_clock
from market_state_builder import build_market_state, load_market_data
from setup_fingerprint import build_setup_fingerprint

st.set_page_config(page_title="Trading Pulse | Replay Lab",page_icon="⏪",layout="wide")
st.markdown("""<style>
.stApp{background:#07090d;color:#f5f7fa}.tp{border:1px solid #242c39;background:#0d1118;border-radius:14px;padding:16px}.gold{color:#d7b45a}.warn{background:#261d08;border:1px solid #d7b45a;padding:12px;border-radius:10px}
</style>""",unsafe_allow_html=True)
st.title("⏪ Trading Pulse Replay Lab")
st.markdown('<div class="warn"><b>REPLAY MODE</b> — future market data is locked. Everything below is rebuilt only from candles at or before the selected historical time.</div>',unsafe_allow_html=True)

c1,c2,c3,c4=st.columns([1.4,1,1,1])
with c1: day=st.date_input("Historical date",value=datetime(2026,8,20).date())
with c2: tm=st.time_input("UTC time",value=datetime(2026,8,20,19,0).time())
with c3: tf=st.selectbox("Chart timeframe",["1m","5m","15m","1H","4H","D"],index=2)
with c4: bars=st.selectbox("Candles",[100,200,300,500],index=1)
selected=pd.Timestamp(datetime.combine(day,tm),tz="UTC")

# Step controls manipulate only the historical clock.
if "replay_ts" not in st.session_state: st.session_state.replay_ts=selected
if selected != st.session_state.get("picker_ts"): st.session_state.replay_ts=selected; st.session_state.picker_ts=selected
b1,b2,b3,b4,b5=st.columns(5)
for col,label,mins in [(b1,"-15m",-15),(b2,"-5m",-5),(b3,"+5m",5),(b4,"+15m",15),(b5,"+1H",60)]:
    if col.button(label,use_container_width=True): st.session_state.replay_ts += pd.Timedelta(minutes=mins)
cutoff=st.session_state.replay_ts; clock=replay_clock(cutoff)
state=build_market_state("GC",clock=clock); fp=build_setup_fingerprint(state,clock=clock)

st.subheader(f"GC as of {clock.cutoff_iso}")
m1,m2,m3,m4,m5=st.columns(5)
m1.metric("Price",f"${state.current_price:,.2f}" if state.current_price else "--")
m2.metric("Bias",str(state.market_bias).upper())
m3.metric("Alignment",f"{state.alignment_score:.1f}%")
m4.metric("Setup",state.setup_state)
m5.metric("Direction",state.setup_direction or "--")

df=load_market_data(tf,limit=bars,as_of=cutoff)
if df is not None and not df.empty:
    chart=df.reset_index().rename(columns={df.index.name or 'index':'timestamp'})
    base=alt.Chart(chart).encode(x=alt.X('timestamp:T',axis=alt.Axis(title=None)),tooltip=['timestamp:T','open:Q','high:Q','low:Q','close:Q'])
    rules=base.mark_rule().encode(y='low:Q',y2='high:Q')
    candles=base.mark_bar(size=5).encode(y='open:Q',y2='close:Q',color=alt.condition('datum.close >= datum.open',alt.value('#22c55e'),alt.value('#ef4444')))
    st.altair_chart((rules+candles).properties(height=520),use_container_width=True)
    st.caption(f"Latest visible candle: {df.index.max()} — hard cutoff: {clock.cutoff_iso}")
else: st.warning("No candles available at this historical point/timeframe.")

left,right=st.columns(2)
with left:
    st.markdown("### What the bot saw")
    st.json({"trends":state.trends,"selected_zone":fp['structure']['execution_zone'],"opposing_zone":fp['structure']['opposing_zone'],"confirmation":fp['confirmation'],"trade":fp['trade']})
with right:
    st.markdown("### Research provenance")
    st.json({"fingerprint_id":fp['fingerprint_id'],"clock":fp['clock'],"market_timestamp":fp['market_timestamp'],"data_symbol":fp['data_symbol'],"engine_versions":fp['engine_versions']})
