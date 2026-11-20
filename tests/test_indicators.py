import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forex_bot.indicators import atr, ema
from forex_bot.models import Rate


class TestIndicators(unittest.TestCase):
    def test_ema_values(self):
        self.assertEqual(ema([1, 2, 3, 4, 5], 3), [2.0, 3.0, 4.0])

    def test_ema_not_enough_data(self):
        self.assertEqual(ema([1, 2], 3), [])

    def test_atr_values(self):
        rates = [
            Rate(time=0, open=10, high=10.5, low=9.5, close=10),
            Rate(time=1, open=10, high=12, low=9, close=10),
            Rate(time=2, open=10, high=11, low=10, close=10.5),
        ]
        result = atr(rates, 2)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0], 2.0)

    def test_atr_not_enough_data(self):
        rates = [Rate(time=0, open=1, high=1, low=1, close=1)]
        self.assertEqual(atr(rates, 14), [])


if __name__ == "__main__":
    unittest.main()
