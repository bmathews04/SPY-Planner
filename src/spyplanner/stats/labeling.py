from __future__ import annotations
import numpy as np
import pandas as pd

def label_target_vs_stop_first(
    df: pd.DataFrame,
    as_of_date: str,
    entry: float,
    stop: float,
    target: float,
    lookahead_bars: int,
) -> int | None:
    """
    Labels outcome scanning forward daily highs/lows.
    Returns:
      1 if target hit before stop
      0 if stop hit before target
      None if neither within horizon (or insufficient future bars)
    """
    idx = df.index
    ts = pd.to_datetime(as_of_date)
    if ts not in idx:
        # align to nearest previous date
        pos = idx.searchsorted(ts)
        pos = min(max(pos - 1, 0), len(idx) - 1)
    else:
        pos = idx.get_loc(ts)

    start = pos + 1
    end = min(len(df), start + lookahead_bars)
    if end <= start:
        return None

    highs = df["High"].iloc[start:end].to_numpy()
    lows = df["Low"].iloc[start:end].to_numpy()

    for h, l in zip(highs, lows):
        if l <= stop:
            return 0
        if h >= target:
            return 1

    return None
