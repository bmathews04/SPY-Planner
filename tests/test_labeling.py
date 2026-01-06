import pandas as pd
from spyplanner.stats.labeling import label_target_vs_stop_first

def test_labeling_hits_target_first():
    df = pd.DataFrame({
        "High": [10, 11, 12, 13],
        "Low":  [9,  9,  9,  9],
        "Open": [9.5, 10, 10.5, 11],
        "Close":[10, 10.5, 11, 12],
        "Volume":[1,1,1,1],
    }, index=pd.date_range("2024-01-01", periods=4, freq="D"))

    label = label_target_vs_stop_first(df, "2024-01-01", entry=10, stop=8, target=12, lookahead_bars=3)
    assert label == 1

def test_labeling_hits_stop_first():
    df = pd.DataFrame({
        "High": [10, 10, 10, 10],
        "Low":  [9,  7,  7,  7],
        "Open": [9.5, 9,  9,  9],
        "Close":[9.7, 8.5, 8.2, 8.1],
        "Volume":[1,1,1,1],
    }, index=pd.date_range("2024-01-01", periods=4, freq="D"))

    label = label_target_vs_stop_first(df, "2024-01-01", entry=10, stop=8, target=12, lookahead_bars=3)
    assert label == 0
