import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forex_bot.config import StrategyConfig, SymbolConfig
from forex_bot.models import Rate
from forex_bot.strategy import EmaAtrStrategy


def make_rates(closes, pip=0.0001):
    rates = []
    for i, c in enumerate(closes):
        half = 5 * pip
        rates.append(Rate(time=i * 300, open=c - half, high=c + half, low=c - half, close=c, tick_volume=100))
    return rates


def make_strategy():
    cfg = StrategyConfig(fast_ema=2, slow_ema=4, atr_period=3, min_atr_pips=1.0,
                         sl_atr_mult=1.5, reward_risk=2.0, max_spread_pips=3.0,
                         session_start_hour=8, session_end_hour=22, lookback_bars=50)
    sym = SymbolConfig(name="EURUSD", pip_size=0.0001, contract_size=100000.0,
                       spread_pips=1.5, slippage_pips=0.5)
    return EmaAtrStrategy(cfg, sym)


class TestStrategy(unittest.TestCase):
    def test_buy_signal_on_bullish_cross(self):
        closes = [1.1000] * 13 + [1.1020]
        strategy = make_strategy()
        signal = strategy.on_rates(make_rates(closes), set(), 1.0, 12)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "buy")
        self.assertLess(signal.sl, closes[-1])
        self.assertGreater(signal.tp, closes[-1])

    def test_sell_signal_on_bearish_cross(self):
        closes = [1.2000] * 13 + [1.1980]
        strategy = make_strategy()
        signal = strategy.on_rates(make_rates(closes), set(), 1.0, 12)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "sell")
        self.assertGreater(signal.sl, closes[-1])
        self.assertLess(signal.tp, closes[-1])

    def test_no_signal_when_spread_too_high(self):
        closes = [1.1000] * 12 + [1.1005, 1.1020]
        strategy = make_strategy()
        self.assertIsNone(strategy.on_rates(make_rates(closes), set(), 10.0, 12))

    def test_no_signal_outside_session(self):
        closes = [1.1000] * 12 + [1.1005, 1.1020]
        strategy = make_strategy()
        self.assertIsNone(strategy.on_rates(make_rates(closes), set(), 1.0, 3))

    def test_no_signal_when_position_already_open(self):
        closes = [1.1000] * 12 + [1.1005, 1.1020]
        strategy = make_strategy()
        self.assertIsNone(strategy.on_rates(make_rates(closes), {"EURUSD"}, 1.0, 12))

    def test_no_signal_without_cross(self):
        closes = [1.1000] * 20
        strategy = make_strategy()
        self.assertIsNone(strategy.on_rates(make_rates(closes), set(), 1.0, 12))

    def test_no_signal_when_atr_too_low(self):
        closes = [1.1000] * 12 + [1.10001, 1.10002]
        strategy = make_strategy()
        self.assertIsNone(strategy.on_rates(make_rates(closes), set(), 1.0, 12))


if __name__ == "__main__":
    unittest.main()
