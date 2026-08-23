# Trading Pulse V4.0A–V4.0F Foundation

This bundle is additive. It does not replace V3.4 dashboard, MarketState, setup scoring,
Elite thresholds, journaling, TradingView rendering, or Professor UI.

## 4A Historical Data Foundation
SQLite canonical OHLCV warehouse, Yahoo reference collector, UTC normalization,
deduplication, coverage and quality auditing, point-in-time reads.

## 4B Replay / Backtest Evidence
Chronological replay clock and evidence warehouse. The replay API never exposes candles
after `as_of`. Existing canonical Trading Pulse engines can be connected by callback.

## 4C Chart Intelligence
Structured chart packet built from multi-timeframe candles plus canonical MarketState and
selected setup payloads. No invented levels.

## 4D Professor Chart Analyst
Prompt contract that separates observed facts, Trading Pulse rules, historical evidence,
interpretation and uncertainty.

## 4E Learning / Telemetry
Question/answer metrics and quarantined claims. New claims default to PENDING and cannot
silently become trusted trading knowledge.

## 4F Verification / Orchestration
Provider-neutral research-verification contract and Professor orchestrator connecting
warehouse, evidence, chart packet and telemetry.

## Important
Yahoo/yfinance remains development/reference data only. It is not execution-grade.
The V4 warehouse is provider-neutral so a future Tradovate/CME-quality adapter can write
to the same canonical schema.

## Next integration pass
1. Populate warehouse.
2. Connect canonical MarketState replay adapter to ReplayClock callback.
3. Store real setup outcomes in EvidenceStore.
4. Connect existing Professor UI/model provider to ProfessorOrchestrator.
5. Add a Research/Backtest dashboard only after evidence is validated.
