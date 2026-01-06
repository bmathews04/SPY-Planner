import numpy as np
import pandas as pd

def slope(series: pd.Series, n: int = 20) -> float:
    s = series.dropna().tail(n)
    if len(s) < n:
        return 0.0
    x = np.arange(n)
    y = s.to_numpy()
    # least squares slope
    x = x - x.mean()
    y = y - y.mean()
    denom = (x * x).sum()
    return float((x * y).sum() / denom) if denom != 0 else 0.0

def classify_regime(row: pd.Series, ema50_slope: float) -> str:
    close = row["Close"]
    ema_mid = row["EMA_MID"]
    ema_slow = row["EMA_SLOW"]
    atr_pctl = row.get("ATR_PCTL", 0.5)

    high_vol = atr_pctl >= 0.75

    # Trend if above/below EMA200 with EMA50 slope aligned
    if close > ema_slow and ema50_slope > 0:
        return "trend_up_highvol" if high_vol else "trend_up"
    if close < ema_slow and ema50_slope < 0:
        return "trend_down_highvol" if high_vol else "trend_down"

    # Range if slope flat-ish
    if abs(ema50_slope) < 0.02:
        return "range_highvol" if high_vol else "range"

    return "mixed_highvol" if high_vol else "mixed"
