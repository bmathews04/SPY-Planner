from __future__ import annotations
import math

def r_multiple(entry: float, stop: float, target: float) -> float:
    risk = abs(entry - stop)
    if risk <= 0:
        return 0.0
    return abs(target - entry) / risk

def suggested_shares(max_risk_dollars: float, entry: float, stop: float) -> int | None:
    if max_risk_dollars <= 0:
        return None
    risk_per_share = abs(entry - stop)
    if risk_per_share <= 0:
        return None
    return int(math.floor(max_risk_dollars / risk_per_share))
