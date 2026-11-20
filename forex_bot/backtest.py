import csv
import tempfile
from datetime import datetime
from pathlib import Path

from .config import Config
from .engine import TradingEngine
from .monitoring import JsonlLogger, TelegramNotifier
from .paper_broker import PaperBroker
from .risk import RiskManager
from .strategy import EmaAtrStrategy
from .models import Rate


def load_csv(path) -> list:
    path = Path(path)
    if not path.exists():
        return []
    rates = []
    with path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            t = row["time"]
            try:
                ts = int(float(t))
            except ValueError:
                ts = int(datetime.fromisoformat(t).timestamp())
            rates.append(
                Rate(
                    time=ts,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    tick_volume=int(float(row.get("tick_volume", 0) or 0)),
                )
            )
    rates.sort(key=lambda r: r.time)
    return rates


def compute_metrics(paper: PaperBroker, equity_curve: list, initial_balance: float) -> dict:
    trades = [t["profit"] for t in paper.closed_trades]
    wins = [p for p in trades if p > 0]
    losses = [p for p in trades if p <= 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    peak = initial_balance
    max_dd = 0.0
    for e in equity_curve:
        peak = max(peak, e)
        if peak > 0:
            max_dd = max(max_dd, (peak - e) / peak)
    net = sum(trades)
    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / len(trades) * 100.0) if trades else 0.0,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0,
        "net_pnl": net,
        "return_pct": (net / initial_balance * 100.0) if initial_balance else 0.0,
        "expectancy": (net / len(trades)) if trades else 0.0,
        "avg_win": (gross_win / len(wins)) if wins else 0.0,
        "avg_loss": (-gross_loss / len(losses)) if losses else 0.0,
        "max_drawdown_pct": max_dd * 100.0,
        "final_equity": paper.account_info().equity,
    }


def run_backtest(cfg: Config, rates: list) -> dict:
    paper = PaperBroker(cfg.symbol, cfg.initial_balance)
    strategy = EmaAtrStrategy(cfg.strategy, cfg.symbol)
    tmp = tempfile.mkdtemp(prefix="forexbot_backtest_")
    risk = RiskManager(cfg.risk, Path(tmp) / "state.json", Path(tmp) / "KILL_SWITCH", cfg.initial_balance)
    logger = JsonlLogger(cfg.log_path)
    engine = TradingEngine(paper, strategy, risk, cfg, logger, TelegramNotifier("", ""), dry_run=False)

    equity_curve = []
    min_bars = max(cfg.strategy.slow_ema, cfg.strategy.atr_period + 1) + 2
    for i in range(min_bars, len(rates)):
        window = rates[max(0, i - cfg.strategy.lookback_bars + 1): i + 1]
        paper.update_rates(window)
        engine.step(datetime.fromtimestamp(window[-1].time))
        equity_curve.append(paper.account_info().equity)

    logger.log("backtest_done", bars=len(rates), symbol=cfg.symbol.name)
    return compute_metrics(paper, equity_curve, cfg.initial_balance)


def format_report(metrics: dict) -> str:
    pf = metrics["profit_factor"]
    pf_str = f"{pf:.2f}" if pf != float("inf") else "inf"
    lines = [
        "=== Rapport de backtest ===",
        f"Trades: {metrics['trades']} (gagnants: {metrics['wins']}, perdants: {metrics['losses']})",
        f"Win rate: {metrics['win_rate']:.1f}% | Profit factor: {pf_str}",
        f"PnL net: {metrics['net_pnl']:.2f} ({metrics['return_pct']:.2f}%) | Expectancy: {metrics['expectancy']:.2f}",
        f"Gain moyen: {metrics['avg_win']:.2f} | Perte moyenne: {metrics['avg_loss']:.2f}",
        f"Max drawdown: {metrics['max_drawdown_pct']:.2f}% | Equity finale: {metrics['final_equity']:.2f}",
    ]
    return "\n".join(lines)
