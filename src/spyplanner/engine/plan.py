from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import numpy as np
import pandas as pd

from spyplanner.config.defaults import default_params
from spyplanner.features.indicators import add_indicators
from spyplanner.features.swings import swings
from spyplanner.features.levels import nearest_zone
from spyplanner.features.regime import slope, classify_regime
from spyplanner.engine.setups import setup_trend_pullback, setup_mean_reversion
from spyplanner.engine.risk import r_multiple, suggested_shares
from spyplanner.stats.analogs import probability_from_db
from spyplanner.storage.db import DB
from spyplanner.engine.explain import explain


@dataclass
class Plan:
    symbol: str
    as_of_date: str
    timeframe: str
    regime: str
    setup_name: str

    last_close: float
    atr14: float

    floor_zone: tuple[float, float] | None
    ceiling_zone: tuple[float, float] | None

    entry_type: str
    entry_price: float
    stop_price: float
    target1_price: float
    target2_price: float

    risk_per_share: float
    r_to_t1: float
    r_to_t2: float

    lookahead_bars: int
    p_target1_before_stop: float | None
    prob_sample: int
    ev_r: float | None

    suggested_shares: int | None
    notes: list[str]

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "as_of_date": self.as_of_date,
            "timeframe": self.timeframe,
            "regime": self.regime,
            "setup": self.setup_name,
            "last_close": self.last_close,
            "atr14": self.atr14,
            "floor_zone": self.floor_zone,
            "ceiling_zone": self.ceiling_zone,
            "entry": {"type": self.entry_type, "price": self.entry_price},
            "risk": {
                "stop": self.stop_price,
                "targets": [self.target1_price, self.target2_price],
                "risk_per_share": self.risk_per_share,
                "R_to_T1": self.r_to_t1,
                "R_to_T2": self.r_to_t2,
            },
            "probability": {
                "lookahead_bars": self.lookahead_bars,
                "p_T1_before_stop": self.p_target1_before_stop,
                "sample": self.prob_sample,
                "ev_R": self.ev_r,
            },
            "suggested_shares": self.suggested_shares,
            "notes": self.notes,
        }


def build_plan(
    symbol: str,
    df: pd.DataFrame,
    lookahead_bars: int,
    stop_atr: float,
    target1_atr: float,
    target2_mult: float,
    max_risk_dollars: float,
    db: DB,
) -> Plan:
    params = default_params()

    # --- Features ---
    f = add_indicators(df, params.ema_fast, params.ema_mid, params.ema_slow, params.atr_n)

    # swings & zones
    sh, sl = swings(f, left=3, right=3)
    f["SWING_HIGH"] = sh
    f["SWING_LOW"] = sl

    last = f.iloc[-1]
    as_of = str(pd.to_datetime(last.name).date())
    last_close = float(last["Close"])
    atrv = float(last["ATR"]) if np.isfinite(last["ATR"]) else float("nan")

    # regime
    ema50_slope = slope(f["EMA_MID"], n=20)
    regime = classify_regime(last, ema50_slope)

    floor_zone = nearest_zone(f["SWING_LOW"], last_close, atrv, width_atr=0.6)
    ceiling_zone = nearest_zone(f["SWING_HIGH"], last_close, atrv, width_atr=0.6)

    # choose setup based on regime
    if regime.startswith("trend_up"):
        setup = setup_trend_pullback(f)
    elif regime.startswith("range"):
        setup = setup_mean_reversion(f)
    else:
        # default to trend pullback as "neutral" but with caution
        setup = setup_trend_pullback(f)
        setup["notes"] = list(setup["notes"]) + ["Regime is mixed; consider reducing size or requiring stronger confirmation."]

    entry_type = setup["entry_type"]
    entry_price = float(setup["entry_price"])

    # Risk/targets: ATR-based baseline, with zone-aware hints via notes
    if not np.isfinite(atrv) or atrv <= 0:
        # fallback if ATR not available
        atrv = max(0.01, last_close * 0.01)

    stop_price = entry_price - stop_atr * atrv
    target1_price = entry_price + target1_atr * atrv
    target2_price = entry_price + (target1_atr * target2_mult) * atrv

    # Zone-aware soft adjustments (conservative)
    # If floor zone exists and it's above the ATR stop, tighten stop to just below zone
    if floor_zone:
        zone_low = floor_zone[0]
        stop_candidate = zone_low - 0.10 * atrv
        stop_price = max(stop_price, stop_candidate)

    # If ceiling zone exists and it's below target2, clamp T2 to near zone
    if ceiling_zone:
        zone_high = ceiling_zone[1]
        target2_price = min(target2_price, zone_high + 0.10 * atrv)

    risk_per_share = abs(entry_price - stop_price)
    r_to_t1 = r_multiple(entry_price, stop_price, target1_price)
    r_to_t2 = r_multiple(entry_price, stop_price, target2_price)

    # log occurrence into db (this builds your probability dataset over time)
    db.insert_occurrence(
        symbol=symbol,
        as_of_date=as_of,
        regime=regime,
        setup_name=setup["name"],
        entry_price=entry_price,
        stop_price=stop_price,
        target1_price=target1_price,
        lookahead_bars=int(lookahead_bars),
    )

    # probability from labeled db occurrences (analogs-based bucketing)
    prob = probability_from_db(
        db=db,
        symbol=symbol,
        regime=regime,
        setup_name=setup["name"],
        lookahead_bars=int(lookahead_bars),
        entry_price=entry_price,
        atr=atrv,
        ema_fast=float(last["EMA_FAST"]),
        ema_mid=float(last["EMA_MID"]),
        atr_pctl=float(last.get("ATR_PCTL", 0.5)),
        stop_atr=stop_atr,
        target1_atr=target1_atr,
    )

    p_t1 = prob.get("p_t1")
    sample = int(prob.get("sample", 0))
    ev_r = prob.get("ev_r")

    shares = suggested_shares(max_risk_dollars, entry_price, stop_price)

    # plan notes
    notes = list(setup.get("notes", []))

    # directional cautions
    if regime.startswith("trend_down"):
        notes.append("Regime is trend down; this long-biased plan is lower quality unless you add a short-side rule set.")
    if floor_zone and last_close < floor_zone[0]:
        notes.append("Price is below the floor zone (support broken); avoid premature entries without stabilization.")
    if ceiling_zone and last_close > ceiling_zone[1]:
        notes.append("Price is above the ceiling zone; upside may be limited / mean reversion risk higher.")

    plan = Plan(
        symbol=symbol,
        as_of_date=as_of,
        timeframe="1D",
        regime=regime,
        setup_name=setup["name"],
        last_close=last_close,
        atr14=atrv,
        floor_zone=floor_zone,
        ceiling_zone=ceiling_zone,
        entry_type=entry_type,
        entry_price=entry_price,
        stop_price=float(stop_price),
        target1_price=float(target1_price),
        target2_price=float(target2_price),
        risk_per_share=float(risk_per_share),
        r_to_t1=float(r_to_t1),
        r_to_t2=float(r_to_t2),
        lookahead_bars=int(lookahead_bars),
        p_target1_before_stop=float(p_t1) if p_t1 is not None else None,
        prob_sample=sample,
        ev_r=float(ev_r) if ev_r is not None else None,
        suggested_shares=shares,
        notes=[],
    )

    # explanation pass
    plan.notes = explain(plan) + notes
    # snapshot log
    db.insert_snapshot(plan)

    return plan
