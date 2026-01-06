import pandas as pd
import numpy as np
from spyplanner.features.indicators import add_indicators

def test_add_indicators_outputs_columns():
    df = pd.DataFrame({
        "Open": [1,2,3,4,5]*100,
        "High": [2,3,4,5,6]*100,
        "Low":  [0.5,1.5,2.5,3.5,4.5]*100,
        "Close":[1.5,2.5,3.5,4.5,5.5]*100,
        "Volume":[100]*500,
    })
    df.index = pd.date_range("2020-01-01", periods=len(df), freq="D")
    out = add_indicators(df, 20, 50, 200, 14)
    assert "EMA_FAST" in out.columns
    assert "ATR" in out.columns
    assert out["EMA_FAST"].notna().sum() > 0
