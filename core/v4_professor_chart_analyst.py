from __future__ import annotations
import json

SYSTEM_RULES = """You are the Trading Pulse Professor chart analyst.
Treat deterministic Trading Pulse MarketState/setup values as authoritative.
Never invent prices, entries, stops, targets, probabilities, news, or backtest statistics.
Separate: OBSERVED CHART FACTS, TRADING PULSE RULES, HISTORICAL EVIDENCE, and PROFESSOR INTERPRETATION.
If evidence is missing, say it is missing. If current external news/calendar context was not supplied,
say it was not checked. Do not silently promote research claims into trading rules."""

def build_professor_prompt(question,chart_packet,evidence=None,verified_knowledge=None):
    return {
      "system":SYSTEM_RULES,
      "question":question,
      "chart_packet":chart_packet,
      "historical_evidence":evidence or {},
      "verified_knowledge":verified_knowledge or [],
      "answer_contract":{
        "direct_answer":"answer the user's question first",
        "sections":["Observed chart facts","Why the setup/levels make sense","Confirmation or invalidation",
                    "Historical evidence","What to watch next","Uncertainty"],
        "no_fabrication":True
      }
    }
