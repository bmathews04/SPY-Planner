from __future__ import annotations
import numpy as np

def explain(plan) -> list[str]:
    notes = []
    notes.append(f"Regime classified as {plan.regime} based on EMA200 position, EMA50 slope, and ATR percentile.")

    if plan.floor_zone and plan.last_close <= plan.floor_zone[1]:
        notes.append("Price is near the floor zone (support); stops under the zone reduce noise-trigger risk.")
    if plan.ceiling_zone and plan.last_close >= plan.ceiling_zone[0]:
        notes.append("Price is near the ceiling zone (resistance); consider taking profits into the zone.")

    if plan.r_to_t1 < 1.0:
        notes.append("R to Target 1 is < 1.0; plan has limited reward relative to risk unless probabilities are high.")

    if plan.p_target1_before_stop is not None and plan.prob_sample < 80:
        notes.append("Probability sample size is small; treat as lower confidence.")

    return notes
