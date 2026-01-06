from __future__ import annotations
import numpy as np

def _bucket_pullback(entry: float, ema_fast: float, atr: float) -> int:
    # pullback depth bucket (in ATR)
    if atr <= 0:
        return 0
    d = (entry - ema_fast) / atr
    # coarse bins
    if d <= -0.8: return -2
    if d <= -0.2: return -1
    if d <= 0.2: return 0
    if d <= 0.8: return 1
    return 2

def _bucket_atr_pctl(p: float) -> int:
    if p < 0.33: return 0
    if p < 0.66: return 1
    return 2

def probability_from_db(
    db,
    symbol: str,
    regime: str,
    setup_name: str,
    lookahead_bars: int,
    entry_price: float,
    atr: float,
    ema_fast: float,
    ema_mid: float,
    atr_pctl: float,
    stop_atr: float,
    target1_atr: float,
) -> dict:
    """
    Read labeled occurrences from sqlite and compute probability based on analog buckets.
    Buckets:
      - regime prefix (trend_up / range / other)
      - pullback bucket (entry vs EMA_FAST in ATR units)
      - ATR percentile bucket
      - stop/target parameters (rounded)
    """
    reg_prefix = regime.split("_")[0]  # "trend" / "range" / "mixed"
    pb = _bucket_pullback(entry_price, ema_fast, atr)
    vb = _bucket_atr_pctl(float(atr_pctl))

    # Round params to reduce fragmentation
    stop_key = round(float(stop_atr), 1)
    tgt_key = round(float(target1_atr), 1)

    rows = db.read_labeled_occurrences(
        symbol=symbol,
        setup_name=setup_name,
        lookahead_bars=int(lookahead_bars),
        reg_prefix=reg_prefix,
        pb_bucket=pb,
        vol_bucket=vb,
        stop_atr=stop_key,
        target1_atr=tgt_key,
        limit=2000,
    )

    if rows is None or len(rows) < 60:
        # widen: drop pb bucket
        rows = db.read_labeled_occurrences(
            symbol=symbol,
            setup_name=setup_name,
            lookahead_bars=int(lookahead_bars),
            reg_prefix=reg_prefix,
            pb_bucket=None,
            vol_bucket=vb,
            stop_atr=stop_key,
            target1_atr=tgt_key,
            limit=5000,
        )

    if rows is None or len(rows) < 60:
        return {"p_t1": None, "sample": 0, "ev_r": None}

    y = rows["label"].to_numpy()
    y = y[np.isfinite(y)]
    if len(y) < 60:
        return {"p_t1": None, "sample": int(len(y)), "ev_r": None}

    p = float(y.mean())
    # EV in R: win = +target/stop R, loss = -1R
    win_R = target1_atr / stop_atr if stop_atr > 0 else 0
    ev_r = p * win_R - (1 - p) * 1.0

    return {"p_t1": p, "sample": int(len(y)), "ev_r": float(ev_r)}
