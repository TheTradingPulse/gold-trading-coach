import pandas as pd
from core.v4_intrabar_resolver import resolve_minutes

def frame(highs,lows):
    return pd.DataFrame({"high":highs,"low":lows},index=pd.date_range("2025-01-01",periods=len(highs),freq="1min",tz="UTC"))

def test_long_target_first(): assert resolve_minutes(frame([101,104],[100,100]),"LONG",100,99,103).result=="TARGET_FIRST"
def test_long_stop_first(): assert resolve_minutes(frame([101,102],[100,98]),"LONG",100,99,103).result=="STOP_FIRST"
def test_same_minute_stays_ambiguous(): assert resolve_minutes(frame([104],[98]),"LONG",100,99,103).result=="SAME_MINUTE_AMBIGUOUS"
def test_short_target_first(): assert resolve_minutes(frame([100,100],[99,96]),"SHORT",100,101,97).result=="TARGET_FIRST"
