from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Recommended:
    stop_atr: float
    target1_atr: float
    target2_mult: float
    lookahead_days: int
    reason: str


def _clip(x: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, x)))


def recommend_trade_params(df: pd.DataFrame) -> Recommended:
    """
    Recommend ATR-based stop/targets based on ticker behavior.
    Uses:
      - ATR% (ATR / Close) median over recent history
      - Gap% (abs(Open - prev Close) / prev Close) 90th percentile
    Both are daily-based and robust.

    Returns explainable, bounded defaults.
    """
    if df is None or df.empty or len(df) < 120:
        # Safe fallback
        return Recommended(
            stop_atr=1.5,
            target1_atr=2.0,
            target2_mult=1.6,
            lookahead_days=20,
            reason="Fallback defaults (insufficient history).",
        )

    d = df.copy()
    d = d.dropna().tail(800)

    close = d["Close"].astype(float)
    atr = d["ATR"].astype(float) if "ATR" in d.columns else None

    # If ATR column isn't present (should be), degrade gracefully:
    if atr is None or atr.isna().all():
        return Recommended(
            stop_atr=1.5,
            target1_atr=2.0,
            target2_mult=1.6,
            lookahead_days=20,
            reason="Fallback defaults (ATR missing).",
        )

    atr_pct = (atr / close).replace([np.inf, -np.inf], np.nan).dropna()
    atr_pct_med = float(atr_pct.tail(252).median()) if len(atr_pct) >= 50 else float(atr_pct.median())

    prev_close = close.shift(1)
    gap_pct = ((d["Open"].astype(float) - prev_close).abs() / prev_close).replace([np.inf, -np.inf], np.nan).dropna()
    gap_90 = float(gap_pct.tail(252).quantile(0.90)) if len(gap_pct) >= 50 else float(gap_pct.quantile(0.90))

    # Volatility score: ATR% dominates, gaps add "spikiness"
    # Typical ranges:
    #   SPY/QQQ: atr_pct_med ~ 0.007–0.012
    #   high beta stocks: 0.02–0.05+
    vol_score = atr_pct_med + 0.6 * gap_90

    # Map to stop/targets (bounded, explainable)
    # Low-vol tickers: slightly tighter stops/targets
    # High-vol tickers: wider stops & larger targets
    if vol_score < 0.010:
        stop = 1.3
        t1 = 1.8
        lookahead = 30
        reason = f"Low daily volatility (ATR%≈{atr_pct_med:.2%}, gap90≈{gap_90:.2%})."
    elif vol_score < 0.018:
        stop = 1.5
        t1 = 2.0
        lookahead = 20
        reason = f"Moderate daily volatility (ATR%≈{atr_pct_med:.2%}, gap90≈{gap_90:.2%})."
    elif vol_score < 0.030:
        stop = 1.8
        t1 = 2.6
        lookahead = 15
        reason = f"High daily volatility (ATR%≈{atr_pct_med:.2%}, gap90≈{gap_90:.2%})."
    else:
        stop = 2.1
        t1 = 3.0
        lookahead = 12
        reason = f"Very high daily volatility (ATR%≈{atr_pct_med:.2%}, gap90≈{gap_90:.2%})."

    # Keep within safe bounds
    stop = _clip(stop, 0.7, 3.5)
    t1 = _clip(t1, 0.8, 6.0)

    return Recommended(
        stop_atr=stop,
        target1_atr=t1,
        target2_mult=1.6,   # keep consistent; it’s a stretch target
        lookahead_days=int(lookahead),
        reason=reason,
    )
