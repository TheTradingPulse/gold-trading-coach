from core.v4_first_touch_contract import classify_first_touch


def test_target_on_earlier_bar_then_stop_is_verified_target_first():
    x=classify_first_touch({"entered":1,"primary_hit":1,"stop_hit":1,
                            "bars_to_primary":2,"bars_to_outcome":7})
    assert x.primary_before_stop and x.primary_class=="TARGET_FIRST_THEN_STOP"


def test_same_bar_is_conservatively_ambiguous_not_a_win():
    x=classify_first_touch({"entered":1,"primary_hit":1,"stop_hit":1,
                            "bars_to_primary":2,"bars_to_outcome":2})
    assert not x.primary_before_stop and x.primary_class=="SAME_BAR_AMBIGUOUS"


def test_stop_without_target_is_stop_first():
    x=classify_first_touch({"entered":1,"primary_hit":0,"stop_hit":1,"bars_to_outcome":1})
    assert not x.primary_before_stop and x.primary_class=="STOP_FIRST"


def test_outcome_json_recovers_missing_columns():
    x=classify_first_touch({"entered":1,"primary_hit":1,"stop_hit":1},
                           {"bars_to_primary":3,"bars_to_outcome":5})
    assert x.primary_before_stop
