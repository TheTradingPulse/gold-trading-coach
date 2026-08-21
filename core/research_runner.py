"""
Trading Pulse V3.1 research runner.
Acquires reference history and executes the real candidate/grading engine.
"""
from __future__ import annotations
from pathlib import Path
import json
from instruments import get_enabled_symbols
from historical_acquisition import acquire_universe
from historical_data_store import HistoricalStore
from canonical_replay_adapter import detector_for_backtest
from historical_backtest_engine import run_point_in_time_backtest,summarize

def run_research(symbols=None,timeframe="1H",store_root="research_data/history",
                 warmup_bars=250,forward_bars=100):
    universe=list(symbols or get_enabled_symbols())
    acquisition=acquire_universe(universe,(timeframe,),store_root)
    store=HistoricalStore(store_root)
    report={"timeframe":timeframe,"markets":{},"acquisition":acquisition}
    for sym in universe:
        hist=store.load(sym,timeframe)
        if len(hist)<=warmup_bars+1:
            report["markets"][sym]={"error":f"insufficient history ({len(hist)} rows)"}
            continue
        events=run_point_in_time_backtest(sym,timeframe,hist,detector_for_backtest,
                                         warmup_bars=warmup_bars,forward_bars=forward_bars)
        report["markets"][sym]={"summary":summarize(events),
                               "events":[e.to_dict() for e in events]}
    return report

def save_report(report,path="research_data/reports/v3_1_research.json"):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(report,indent=2),encoding="utf-8")
    return str(p)
