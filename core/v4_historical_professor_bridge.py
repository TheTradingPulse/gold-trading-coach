from __future__ import annotations
from pathlib import Path
import json, re
import pandas as pd
from .v4_blind_library import BlindHistoricalLibrary

class HistoricalProfessorBridge:
    """Facts-only bridge. It returns data packets; the Professor must not invent missing facts."""
    def __init__(self, library=None, validation_root=r"C:\TradingPulse\research_data\v4\five_year_blind_validation"):
        self.library=library or BlindHistoricalLibrary()
        self.validation_root=Path(validation_root)

    def chart_packet(self, symbol, date, timeframe="15m", days=1):
        start=pd.Timestamp(date, tz="UTC") if pd.Timestamp(date).tzinfo is None else pd.Timestamp(date).tz_convert("UTC")
        end=start+pd.Timedelta(days=days)
        df=self.library.read_range(symbol.upper(),start,end,timeframe)
        return {"kind":"historical_chart","symbol":symbol.upper(),"start":str(start),"end":str(end),
                "timeframe":timeframe,"bars":df.reset_index().to_dict("records")}

    def validation_summary(self):
        p=self.validation_root/"blind_validation_summary.json"
        if not p.exists():
            return {"kind":"validation_summary","status":"INSUFFICIENT DATA","reason":"blind validation report not built"}
        return json.loads(p.read_text(encoding="utf-8"))

    def route(self, question):
        q=question.lower()
        m=re.search(r"\b(gc|si|es|nq|ym|rty|cl|ng)\b",q)
        symbol=m.group(1).upper() if m else None
        date=re.search(r"\b(20\d{2}-\d{2}-\d{2})\b",q)
        if symbol and date and ("chart" in q or "pull up" in q or "show" in q):
            return self.chart_packet(symbol,date.group(1))
        if any(x in q for x in ("elite","grand slam","win rate","backtest","validation")):
            return {"kind":"validation_summary","data":self.validation_summary()}
        return {"kind":"unsupported_historical_query","status":"INSUFFICIENT DATA",
                "reason":"Historical bridge could not safely resolve the requested facts."}
