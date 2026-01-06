import numpy as np
import pandas as pd

def swings(df: pd.DataFrame, left: int = 3, right: int = 3) -> tuple[pd.Series, pd.Series]:
    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()

    sh = np.full(len(df), np.nan, dtype=float)
    sl = np.full(len(df), np.nan, dtype=float)

    for i in range(left, len(df) - right):
        wh = highs[i-left:i+right+1]
        wl = lows[i-left:i+right+1]
        if highs[i] == np.max(wh) and np.sum(wh == highs[i]) == 1:
            sh[i] = highs[i]
        if lows[i] == np.min(wl) and np.sum(wl == lows[i]) == 1:
            sl[i] = lows[i]

    return pd.Series(sh, index=df.index, name="SWING_HIGH"), pd.Series(sl, index=df.index, name="SWING_LOW")
