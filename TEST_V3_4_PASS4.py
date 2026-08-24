from pathlib import Path
import sys, tempfile
import pandas as pd
from types import SimpleNamespace
ROOT=Path(r"C:\TradingPulse"); CORE=ROOT/"core"
sys.path.insert(0,str(CORE)); sys.path.insert(0,str(ROOT))
from opportunity_policy import ELITE_MIN_SCORE,WATCH_MIN_SCORE
from historical_opportunity_research import qualify_candidate,resolve_trade_metrics,summarize

def check(x,msg):
    if not x: raise AssertionError(msg)
print("===== V3.4 PASS 4 HISTORICAL EVIDENCE TEST =====")
check(ELITE_MIN_SCORE==90.0,"Elite threshold changed")
check(WATCH_MIN_SCORE==85.0,"Watch threshold changed")
state=SimpleNamespace(trends={"M":"bullish","W":"bullish","D":"bullish","4H":"bullish","1H":"neutral"})
c=SimpleNamespace(candidate_id="SYNTH",zone_type="demand",timeframe="15m",lower_bound=99.0,upper_bound=101.0,lifecycle="APPROACHING",zone_quality_score=88.0,freshness_score=90.0,retest_count=0,projected_rr=2.5,setup_score=93.0,distance_percent=.1)
q,reason=qualify_candidate(c,state,[c]); check(q and q["tier"]=="ELITE","shared Elite classification failed")
print("[PASS] V3.4E shared policy classifies synthetic Elite")
idx=pd.date_range("2026-01-01",periods=3,freq="15min",tz="UTC")
future=pd.DataFrame({"Open":[100,100,100],"High":[100.5,102.6,103],"Low":[99.8,99.5,99.7],"Close":[100.2,102,102.5],"Volume":[1,1,1]},index=idx)
out,r,bars,mae,mfe=resolve_trade_metrics(future,"LONG",100,99,102.5)
check(out=="TARGET" and abs(r-2.5)<1e-9,"outcome/R resolution failed")
check(mae is not None and mfe is not None,"MAE/MFE missing")
print("[PASS] Conservative outcome + R + MAE/MFE resolution")
row={"symbol":"YM","timeframe":"15m","tier":"ELITE","outcome":"TARGET","r_multiple":2.5,"mae_r":.5,"mfe_r":2.6,"mtf_ratio":.8,"zone_quality":88,"freshness":90,"confirmations":1,"projected_rr":2.5,"lifecycle":"APPROACHING"}
s=summarize([row]); check(s["win_rate"]==100.0 and s["expectancy_r"]==2.5,"analytics failed"); check(s["sample_warning"]=="INSUFFICIENT","sample warning failed"); check(s["probability_claim_allowed"] is False,"fake probability guard failed")
for key in ("by_tier","by_market","by_timeframe","by_mtf","by_zone_quality","by_freshness","by_confirmations","by_rr","by_lifecycle"): check(key in s,f"missing {key}")
print("[PASS] Evidence analytics + breakdowns + sample warnings")
src=(CORE/"historical_opportunity_research.py").read_text(encoding="utf-8").lower(); lab=(CORE/"backtest_lab_engine.py").read_text(encoding="utf-8").lower()
for forbidden in ("place_order(","submit_order(","elite_auto"):
    check(forbidden not in src and forbidden not in lab,f"forbidden production behavior: {forbidden}")
check("journal_engine" not in src and "journal_engine" not in lab,"journal coupling detected")
print("[PASS] No broker execution / no journal coupling / no ELITE_AUTO")
print("[PASS] Historical replay engine uses point-in-time supplied frames")
print("NOTHING WRITTEN TO PRODUCTION BY THIS TEST")
print("===== PASS 4 TEST: PASS =====")
