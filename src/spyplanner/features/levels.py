from __future__ import annotations
import numpy as np
import pandas as pd

def nearest_zone(levels: pd.Series, price: float, atr: float, width_atr: float = 0.6, tail: int = 40):
    lv = levels.dropna().tail(tail)
    if lv.empty or not np.isfinite(atr) or atr <= 0:
        return None

    nearest = float(lv.iloc[(lv - price).abs().argmin()])
    w = max(width_atr * atr, 0.01)
    return (round(nearest - w, 4), round(nearest + w, 4))
