import csv
import math
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forex_bot.backtest import compute_metrics, load_csv, run_backtest
from forex_bot.config import (Config, ExecutionConfig, Mt5Config, RiskConfig,
                              StrategyConfig, SymbolConfig, TelegramConfig)
from forex_bot.models import Rate
from forex_bot.paper_broker import PaperBroker


def make_rates(n=400):
    t0 = int(datetime(2025, 1, 6, 10, 0, 0).timestamp())
    rates = []
    for i in range(n):
        mid = 1.10 + 0.004 * math.sin(i / 8.0)
        rates.append(Rate(time=t0 + i * 300, open=mid, high=mid + 0.0008, low=mid - 0.0008, close=mid, tick_volume=100))
    return rates


def make_config(tmp):
    return Config(
        mt5=Mt5Config(),
        symbol=SymbolConfig(name="EURUSD", pip_size=0.0001, contract_size=100000.0,
                            spread_pips=1.5, slippage_pips=0.5),
        strategy=StrategyConfig(fast_ema=9, slow_ema=21, atr_period=14, min_atr_pips=1.0,
                                sl_atr_mult=1.5, reward_risk=2.0, max_spread_pips=3.0,
                                session_start_hour=8, session_end_hour=22, lookback_bars=200),
        risk=RiskConfig(),
        execution=ExecutionConfig(mode="backtest", dry_run=False),
        telegram=TelegramConfig(),
        initial_balance=10000.0,
        log_path=str(Path(tmp) / "logs" / "trades.jsonl"),
    )


class TestBacktest(unittest.TestCase):
    def test_run_backtest_returns_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            metrics = run_backtest(make_config(tmp), make_rates())
            for key in ("trades", "win_rate", "profit_factor", "net_pnl", "max_drawdown_pct", "final_equity"):
                self.assertIn(key, metrics)
            self.assertGreater(metrics["trades"], 0)
            self.assertGreater(metrics["final_equity"], 0)

    def test_load_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.csv"
            with path.open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["time", "open", "high", "low", "close", "tick_volume"])
                writer.writerow([1736164800, 1.1, 1.11, 1.09, 1.105, 100])
                writer.writerow([1736164500, 1.09, 1.10, 1.08, 1.095, 80])
            rates = load_csv(path)
            self.assertEqual(len(rates), 2)
            self.assertLessEqual(rates[0].time, rates[1].time)
            self.assertAlmostEqual(rates[0].close, 1.095)

    def test_load_csv_missing_file(self):
        self.assertEqual(load_csv("/nonexistent/file.csv"), [])

    def test_compute_metrics_empty(self):
        paper = PaperBroker(make_config(tempfile.mkdtemp()).symbol, 10000.0)
        metrics = compute_metrics(paper, [10000.0, 10100.0], 10000.0)
        self.assertEqual(metrics["trades"], 0)
        self.assertEqual(metrics["max_drawdown_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
