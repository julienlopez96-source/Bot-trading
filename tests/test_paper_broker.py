import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forex_bot.config import SymbolConfig
from forex_bot.models import Rate
from forex_bot.paper_broker import PaperBroker


def make_symbol():
    return SymbolConfig(name="EURUSD", pip_size=0.0001, contract_size=100000.0,
                        spread_pips=2.0, slippage_pips=0.0, min_lot=0.01, lot_step=0.01, max_lot=100.0)


def bar(i, close, spread=0.0005):
    return Rate(time=i * 300, open=close, high=close + spread, low=close - spread, close=close, tick_volume=100)


class TestPaperBroker(unittest.TestCase):
    def test_buy_order_fill_includes_half_spread(self):
        broker = PaperBroker(make_symbol(), 10000.0)
        broker.update_rates([bar(0, 1.1000)])
        res = broker.market_order("EURUSD", 1.0, "buy", 1.0950, 1.1100)
        self.assertTrue(res.success)
        self.assertAlmostEqual(res.price, 1.1001)
        self.assertEqual(len(broker.get_positions()), 1)

    def test_stop_loss_closes_position_with_loss(self):
        broker = PaperBroker(make_symbol(), 10000.0)
        broker.update_rates([bar(0, 1.1000)])
        res = broker.market_order("EURUSD", 1.0, "buy", 1.0950, 1.1100)
        broker.update_rates([bar(0, 1.1000), bar(1, 1.0990, spread=0.0060)])
        self.assertEqual(len(broker.get_positions()), 0)
        profit = broker.get_closed_profit(res.ticket)
        self.assertAlmostEqual(profit, (1.0950 - 1.1001) * 100000.0)
        self.assertAlmostEqual(broker.account_info().balance, 10000.0 + profit)
        self.assertEqual(len(broker.closed_trades), 1)

    def test_take_profit_closes_position_with_gain(self):
        broker = PaperBroker(make_symbol(), 10000.0)
        broker.update_rates([bar(0, 1.1000)])
        res = broker.market_order("EURUSD", 1.0, "buy", 1.0950, 1.1100)
        broker.update_rates([bar(0, 1.1000), bar(1, 1.1090, spread=0.0020)])
        self.assertEqual(len(broker.get_positions()), 0)
        profit = broker.get_closed_profit(res.ticket)
        self.assertAlmostEqual(profit, (1.1100 - 1.1001) * 100000.0)
        self.assertGreater(profit, 0)

    def test_sell_order_stop_loss(self):
        broker = PaperBroker(make_symbol(), 10000.0)
        broker.update_rates([bar(0, 1.1000)])
        res = broker.market_order("EURUSD", 0.5, "sell", 1.1050, 1.0900)
        broker.update_rates([bar(0, 1.1000), bar(1, 1.1060, spread=0.0020)])
        self.assertEqual(len(broker.get_positions()), 0)
        profit = broker.get_closed_profit(res.ticket)
        self.assertAlmostEqual(profit, (1.0999 - 1.1050) * 0.5 * 100000.0)
        self.assertLess(profit, 0)

    def test_close_all(self):
        broker = PaperBroker(make_symbol(), 10000.0)
        broker.update_rates([bar(0, 1.1000)])
        broker.market_order("EURUSD", 0.1, "buy", 1.0950, 1.1100)
        broker.market_order("EURUSD", 0.1, "sell", 1.1050, 1.0900)
        self.assertEqual(broker.close_all(), 2)
        self.assertEqual(len(broker.get_positions()), 0)

    def test_order_without_data_fails(self):
        broker = PaperBroker(make_symbol(), 10000.0)
        res = broker.market_order("EURUSD", 1.0, "buy", 1.0950, 1.1100)
        self.assertFalse(res.success)


if __name__ == "__main__":
    unittest.main()
