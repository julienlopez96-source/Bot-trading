import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from forex_bot.backtest import format_report, load_csv, run_backtest
from forex_bot.config import load_config
from forex_bot.engine import TradingEngine
from forex_bot.monitoring import JsonlLogger, TelegramNotifier
from forex_bot.mt5_broker import MT5Broker
from forex_bot.news import NewsManager
from forex_bot.news_strategy import NewsStrategy
from forex_bot.risk import RiskManager
from forex_bot.strategy import EmaAtrStrategy


def main():
    parser = argparse.ArgumentParser(description="Bot de day trading Forex (MetaTrader 5)")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--mode", choices=["backtest", "live"], help="backtest = CSV historique, live = connexion MT5")
    parser.add_argument("--data", help="Fichier CSV pour le backtest (colonnes time,open,high,low,close,tick_volume)")
    parser.add_argument("--dry-run", action="store_true", help="Aucun ordre réel envoyé (paper trading)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    logger = JsonlLogger(cfg.log_path)
    notifier = TelegramNotifier(cfg.telegram.bot_token, cfg.telegram.chat_id)
    mode = args.mode or cfg.execution.mode

    if mode == "backtest":
        data_path = args.data or cfg.backtest_data
        rates = load_csv(data_path)
        if not rates:
            print(f"Aucune donnée lisible dans {data_path}")
            return 1
        metrics = run_backtest(cfg, rates)
        print(format_report(metrics))
        return 0

    broker = MT5Broker(cfg.mt5, cfg.symbol, cfg.execution)
    if not broker.connect():
        print("Connexion MT5 impossible : terminal ouvert, compte connecté, identifiants corrects ?")
        return 1
    risk = RiskManager(cfg.risk, cfg.state_path, cfg.kill_switch_path, cfg.initial_balance)
    strategy = EmaAtrStrategy(cfg.strategy, cfg.symbol)
    news = NewsManager(cfg.news, cfg.symbol.name, logger) if cfg.news.enabled else None
    news_strategy = NewsStrategy(cfg.news, cfg.symbol, cfg.strategy.atr_period) if cfg.news.enabled else None
    dry = args.dry_run or cfg.execution.dry_run
    engine = TradingEngine(broker, strategy, risk, cfg, logger, notifier, dry_run=dry, news=news, news_strategy=news_strategy)
    try:
        engine.run()
    except KeyboardInterrupt:
        logger.log("engine_stop", reason="keyboard_interrupt")
    finally:
        broker.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
