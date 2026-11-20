import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forex_bot.config import RiskConfig, SymbolConfig
from forex_bot.risk import RiskManager


def make_risk(tmp, **overrides):
    params = dict(risk_per_trade_pct=1.0, max_daily_loss_pct=3.0, max_drawdown_pct=10.0,
                  max_open_positions=1, max_consecutive_losses=3, cooldown_minutes=60,
                  force_close_hour=22)
    params.update(overrides)
    cfg = RiskConfig(**params)
    return RiskManager(cfg, Path(tmp) / "state.json", Path(tmp) / "KILL_SWITCH", 10000.0)


def make_symbol():
    return SymbolConfig(name="EURUSD", pip_size=0.0001, contract_size=100000.0,
                        spread_pips=1.5, slippage_pips=0.5, min_lot=0.01, lot_step=0.01, max_lot=100.0)


class TestRiskManager(unittest.TestCase):
    def test_size_position(self):
        with tempfile.TemporaryDirectory() as tmp:
            rm = make_risk(tmp)
            lots = rm.size_position(10000.0, 1.1000, 1.0950, make_symbol())
            self.assertAlmostEqual(lots, 0.2)

    def test_size_position_zero_sl_distance(self):
        with tempfile.TemporaryDirectory() as tmp:
            rm = make_risk(tmp)
            self.assertEqual(rm.size_position(10000.0, 1.1000, 1.1000, make_symbol()), 0.0)

    def test_size_position_below_min_lot(self):
        with tempfile.TemporaryDirectory() as tmp:
            rm = make_risk(tmp)
            self.assertEqual(rm.size_position(100.0, 1.1000, 1.0950, make_symbol()), 0.0)

    def test_size_position_capped_at_max_lot(self):
        with tempfile.TemporaryDirectory() as tmp:
            rm = make_risk(tmp)
            lots = rm.size_position(1000000.0, 1.1000, 1.0999, make_symbol())
            self.assertAlmostEqual(lots, 100.0)

    def test_can_trade_normal(self):
        with tempfile.TemporaryDirectory() as tmp:
            rm = make_risk(tmp)
            ok, reason = rm.can_trade(datetime.now(), 10000.0)
            self.assertTrue(ok)
            self.assertEqual(reason, "")

    def test_daily_loss_limit_blocks_trading(self):
        with tempfile.TemporaryDirectory() as tmp:
            rm = make_risk(tmp)
            now = datetime.now()
            rm.record_result(-200.0, now, 10000.0)
            rm.record_result(-200.0, now, 10000.0)
            ok, reason = rm.can_trade(now, 10000.0)
            self.assertFalse(ok)
            self.assertEqual(reason, "daily_loss_limit")

    def test_drawdown_limit_blocks_trading(self):
        with tempfile.TemporaryDirectory() as tmp:
            rm = make_risk(tmp)
            rm.state["peak_equity"] = 10000.0
            ok, reason = rm.can_trade(datetime.now(), 8900.0)
            self.assertFalse(ok)
            self.assertEqual(reason, "max_drawdown")

    def test_kill_switch_blocks_trading(self):
        with tempfile.TemporaryDirectory() as tmp:
            rm = make_risk(tmp)
            (Path(tmp) / "KILL_SWITCH").touch()
            ok, reason = rm.can_trade(datetime.now(), 10000.0)
            self.assertFalse(ok)
            self.assertEqual(reason, "kill_switch")

    def test_cooldown_after_consecutive_losses(self):
        with tempfile.TemporaryDirectory() as tmp:
            rm = make_risk(tmp)
            now = datetime.now()
            for _ in range(3):
                rm.record_result(-10.0, now, 10000.0)
            ok, reason = rm.can_trade(now, 10000.0)
            self.assertFalse(ok)
            self.assertEqual(reason, "cooldown")
            rm.state["cooldown_until"] = (now - timedelta(minutes=1)).isoformat()
            ok, _ = rm.can_trade(now, 10000.0)
            self.assertTrue(ok)

    def test_win_resets_consecutive_losses(self):
        with tempfile.TemporaryDirectory() as tmp:
            rm = make_risk(tmp)
            now = datetime.now()
            rm.record_result(-10.0, now, 10000.0)
            rm.record_result(-10.0, now, 10000.0)
            rm.record_result(50.0, now, 10000.0)
            self.assertEqual(rm.state["consecutive_losses"], 0)


if __name__ == "__main__":
    unittest.main()
