import numpy as np
import pandas as pd

def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr

def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return true_range(df).rolling(n).mean()

def add_indicators(df: pd.DataFrame, ema_fast: int, ema_mid: int, ema_slow: int, atr_n: int) -> pd.DataFrame:
    out = df.copy()
    out["EMA_FAST"] = ema(out["Close"], ema_fast)
    out["EMA_MID"] = ema(out["Close"], ema_mid)
    out["EMA_SLOW"] = ema(out["Close"], ema_slow)
    out["ATR"] = atr(out, atr_n)
    # ATR percentile for regime
    out["ATR_PCTL"] = out["ATR"].rank(pct=True)
    return out
