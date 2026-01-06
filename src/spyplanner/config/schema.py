from dataclasses import dataclass

@dataclass(frozen=True)
class PlanParams:
    stop_atr: float = 1.5
    target1_atr: float = 2.0
    target2_mult: float = 1.6
    ema_fast: int = 20
    ema_mid: int = 50
    ema_slow: int = 200
    atr_n: int = 14
