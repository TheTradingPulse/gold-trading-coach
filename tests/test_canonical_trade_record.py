from core.canonical_contracts import CanonicalTradeRecord


def valid_trade(**updates):
    values = dict(
        trade_id="GC-20260820-0900-LONG", detector_version="TP_SETUP_1",
        symbol="GC", contract="GCZ6", setup_family="TREND_PULLBACK",
        direction="LONG", context_timeframe="4H", execution_timeframe="15m",
        detected_at="2026-08-20T08:45:00-04:00",
        confirmed_at="2026-08-20T09:00:00-04:00",
        entry=4537.0, stop=4521.0, target_1r=4553.0,
        target_2r=4569.0, target_3r=4585.0,
        risk_points=16.0, risk_ticks=160.0, risk_dollars=160.0, quantity=1,
        structure_4h="BULLISH", structure_1h="BULLISH",
        confirmation_15m=True, opposing_level=4580.0,
        available_room_r=2.6875, data_split="HOLDOUT", data_source="DATABENTO",
    )
    values.update(updates)
    return CanonicalTradeRecord(**values)


def test_valid_trade_is_one_consistent_record():
    assert valid_trade().validate() == []


def test_risk_ceiling_is_maximum_not_default():
    assert "risk_exceeds_maximum" not in valid_trade(risk_dollars=75.0).validate()
    assert "risk_exceeds_maximum" in valid_trade(risk_dollars=310.0).validate()


def test_targets_cannot_drift_between_reports():
    assert "target_2r_mismatch" in valid_trade(target_2r=4572.0).validate()


def test_outcome_cannot_appear_without_versioned_resolver():
    assert "resolved_outcome_version_missing" in valid_trade(outcome_status="TARGET_2R").validate()
