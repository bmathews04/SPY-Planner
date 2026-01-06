from spyplanner.config.schema import PlanParams

def default_params() -> PlanParams:
    # Daily-first defaults
    return PlanParams(
        stop_atr=1.5,
        target1_atr=2.0,
        target2_mult=1.6,
        ema_fast=20,
        ema_mid=50,
        ema_slow=200,
        atr_n=14,
    )
