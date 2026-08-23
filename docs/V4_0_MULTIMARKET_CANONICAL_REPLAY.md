# V4.0 Multi-Market Canonical Replay

Universe: GC, SI, ES, NQ, YM, RTY, CL, NG.

This pass connects the V4 warehouse to the existing canonical MarketState and
SetupCandidate engines without changing their scoring rules. Historical states
are created through an explicit as-of warehouse boundary. Future candles are
used only after candidate creation to evaluate outcomes.

Outcome handling is deliberately conservative: if an OHLC bar contains both a
stop and a target after entry, the stop wins the ambiguous same-bar ordering.

Yahoo remains reference/development data, not execution-grade data. 4H bars
retain Yahoo provenance and are derived from 1H by the V4 collector.

This bundle does NOT alter V3.4 dashboard, Elite threshold, auto-journal,
Professor UI, TradingView renderer, or canonical setup scoring.
