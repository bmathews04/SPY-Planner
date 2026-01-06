from __future__ import annotations
import numpy as np
import pandas as pd

def setup_trend_pullback(df: pd.DataFrame) -> dict:
    """
    Daily trend pullback:
    - Precondition: close above EMA_SLOW and EMA_MID slope up (handled by regime)
    - Entry idea: limit near EMA_FAST
    - Confirmation isn't enforced here (plan-only). Notes handle confirmation guidance.
    """
    last = df.iloc[-1]
    entry = float(last["EMA_FAST"])
    return {
        "name": "trend_pullback",
        "entry_type": "limit",
        "entry_price": entry,
        "notes": [
            "Trend pullback plan: consider waiting for a close back above EMA_FAST after a pullback.",
            "Avoid entering mid-air; prefer entry near EMA_FAST or after reclaim confirmation."
        ],
    }

def setup_mean_reversion(df: pd.DataFrame) -> dict:
    """
    Daily mean reversion to value (range):
    - Entry idea: limit near EMA_FAST, but only if price stretched below it
    - If price already above EMA_FAST, plan is less attractive.
    """
    last = df.iloc[-1]
    close = float(last["Close"])
    ema_fast = float(last["EMA_FAST"])
    atr = float(last["ATR"]) if np.isfinite(last["ATR"]) else np.nan

    entry = ema_fast
    notes = ["Mean reversion plan: aim for reversion back toward EMA_FAST / value."]

    if np.isfinite(atr) and close > ema_fast + 0.8 * atr:
        notes.append("Price is already extended above value; mean reversion long has weaker edge here.")
    if np.isfinite(atr) and close < ema_fast - 0.8 * atr:
        notes.append("Stretched below value; reversion setup is more relevant (watch for stabilization).")

    return {
        "name": "mean_reversion",
        "entry_type": "limit",
        "entry_price": float(entry),
        "notes": notes,
    }
