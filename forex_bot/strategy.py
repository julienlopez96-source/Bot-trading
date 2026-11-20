from .config import StrategyConfig, SymbolConfig
from .indicators import atr, ema
from .models import Rate, Signal


class EmaAtrStrategy:
    def __init__(self, cfg: StrategyConfig, symbol_cfg: SymbolConfig):
        self.cfg = cfg
        self.sym = symbol_cfg

    def on_rates(self, rates: list, open_symbols: set, current_spread_pips: float, now_hour: int):
        c = self.cfg
        min_bars = max(c.slow_ema, c.atr_period + 1) + 2
        if len(rates) < min_bars:
            return None
        if now_hour < c.session_start_hour or now_hour >= c.session_end_hour:
            return None
        if self.sym.name in open_symbols:
            return None
        if current_spread_pips > c.max_spread_pips:
            return None

        closes = [r.close for r in rates]
        fast = ema(closes, c.fast_ema)
        slow = ema(closes, c.slow_ema)
        atr_values = atr(rates, c.atr_period)
        if len(fast) < 2 or len(slow) < 2 or not atr_values:
            return None

        atr_now = atr_values[-1]
        if atr_now / self.sym.pip_size < c.min_atr_pips:
            return None

        if fast[-2] <= slow[-2] and fast[-1] > slow[-1]:
            direction = "buy"
        elif fast[-2] >= slow[-2] and fast[-1] < slow[-1]:
            direction = "sell"
        else:
            return None

        entry = rates[-1].close
        sl_dist = atr_now * c.sl_atr_mult
        if direction == "buy":
            sl = entry - sl_dist
            tp = entry + sl_dist * c.reward_risk
        else:
            sl = entry + sl_dist
            tp = entry - sl_dist * c.reward_risk
        return Signal(symbol=self.sym.name, direction=direction, sl=sl, tp=tp, reason="ema_cross")
