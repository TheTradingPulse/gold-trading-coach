# Trading Pulse V4 Contextual Evidence Replay

Research-only contextual replay for GC, SI, ES, NQ, YM, RTY, CL and NG.

Design rules:
- strict point-in-time warehouse boundary through the canonical replay adapter
- no fabricated chart context; missing data remains missing
- separate `context_evidence_v4.db`; Evidence V3 is not mutated
- 3R primary and 5R stretch outcomes remain authoritative
- market/setup/direction identity gates contextual comparables
- contextual features refine evidence using session, trend, volatility, HTF alignment, zone/reason fields and risk geometry
- Professor adapter consumes the same contextual evidence packet
- V3.4 live trading policy is not imported or modified by this package
