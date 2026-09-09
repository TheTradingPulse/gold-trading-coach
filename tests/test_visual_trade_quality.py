from core.visual_trade_quality import VisualTrade, evaluate_visual_trade


def test_accepts_confirmed_bullish_continuation_with_room_and_risk():
    decision = evaluate_visual_trade(VisualTrade(
        direction="LONG", structure_4h="BULLISH", structure_1h="BULLISH",
        confirmation_15m=True, countertrend_reversal_confirmed=False,
        entry=4537.0, stop=4521.0, opposing_level=4577.0,
    ))
    assert decision.accepted
    assert decision.setup_type == "TREND_CONTINUATION"
    assert decision.risk_dollars == 160.0
    assert decision.room_r == 2.5


def test_rejects_falling_knife_long_even_if_zone_was_touched():
    decision = evaluate_visual_trade(VisualTrade(
        direction="LONG", structure_4h="BEARISH", structure_1h="BEARISH",
        confirmation_15m=False, countertrend_reversal_confirmed=False,
        entry=4441.6, stop=4426.0, opposing_level=4480.0,
    ))
    assert not decision.accepted
    assert "NO_15M_CONFIRMATION" in decision.reasons
    assert "COUNTERTREND_WITHOUT_REVERSAL_CONFIRMATION" in decision.reasons


def test_rejects_good_looking_trade_that_exceeds_risk_ceiling():
    decision = evaluate_visual_trade(VisualTrade(
        direction="LONG", structure_4h="BULLISH", structure_1h="BULLISH",
        confirmation_15m=True, countertrend_reversal_confirmed=False,
        entry=4577.0, stop=4521.0, opposing_level=4690.0,
    ))
    assert not decision.accepted
    assert "RISK_EXCEEDS_MAXIMUM" in decision.reasons
