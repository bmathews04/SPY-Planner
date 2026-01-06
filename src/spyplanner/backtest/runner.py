from __future__ import annotations
import numpy as np
import pandas as pd

from spyplanner.features.indicators import add_indicators
from spyplanner.features.regime import slope, classify_regime
from spyplanner.engine.setups import setup_trend_pullback, setup_mean_reversion
from spyplanner.stats.labeling import label_target_vs_stop_first

def quick_backtest(df: pd.DataFrame, setup_name: str, stop_atr: float, target1_atr: float, target2_mult: float):
    """
    Simplified daily backtest:
    - Each day generates a plan (entry at EMA_FAST)
    - Labels outcome for T1 vs stop within 20 bars (fixed horizon for this quick view)
    - This is to sanity check; probabilities come from the DB labeling pipeline.
    """
    f = add_indicators(df, ema_fast=20, ema_mid=50, ema_slow=200, atr_n=14).dropna()

    lookahead = 20
    trades = []

    for i in range(250, len(f) - lookahead - 1):
        window = f.iloc[: i + 1]
        last = window.iloc[-1]
        atr = float(last["ATR"]) if np.isfinite(last["ATR"]) else 0.0
        if atr <= 0:
            continue

        ema50_slope = slope(window["EMA_MID"], n=20)
        regime = classify_regime(last, ema50_slope)

        if setup_name == "mean_reversion":
            setup = setup_mean_reversion(window)
        else:
            setup = setup_trend_pullback(window)

        entry = float(setup["entry_price"])
        stop = entry - stop_atr * atr
        t1 = entry + target1_atr * atr

        as_of = str(pd.to_datetime(window.index[-1]).date())
        label = label_target_vs_stop_first(df=f, as_of_date=as_of, entry=entry, stop=stop, target=t1, lookahead_bars=lookahead)
        if label is None:
            continue

        trades.append({
            "date": as_of,
            "regime": regime,
            "setup": setup["name"],
            "entry": entry,
            "stop": stop,
            "t1": t1,
            "label_t1": label,
        })

    tdf = pd.DataFrame(trades)
    if tdf.empty:
        return {"summary": {"trades": 0}, "trades": tdf}

    win_rate = float(tdf["label_t1"].mean())
    summary = {
        "trades": int(len(tdf)),
        "win_rate_T1": win_rate,
    }
    return {"summary": summary, "trades": tdf}
