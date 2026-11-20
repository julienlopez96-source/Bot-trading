import dataclasses
import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Mt5Config:
    login: int = 0
    password: str = ""
    server: str = ""
    path: str = ""
    timeout: int = 60000


@dataclass
class SymbolConfig:
    name: str = "EURUSD"
    pip_size: float = 0.0001
    contract_size: float = 100000.0
    spread_pips: float = 1.5
    slippage_pips: float = 0.5
    min_lot: float = 0.01
    lot_step: float = 0.01
    max_lot: float = 10.0


@dataclass
class StrategyConfig:
    fast_ema: int = 9
    slow_ema: int = 21
    atr_period: int = 14
    min_atr_pips: float = 5.0
    sl_atr_mult: float = 1.5
    reward_risk: float = 2.0
    max_spread_pips: float = 3.0
    session_start_hour: int = 8
    session_end_hour: int = 22
    lookback_bars: int = 200


@dataclass
class RiskConfig:
    risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 3.0
    max_drawdown_pct: float = 10.0
    max_open_positions: int = 1
    max_consecutive_losses: int = 3
    cooldown_minutes: int = 60
    force_close_hour: int = 22


@dataclass
class ExecutionConfig:
    mode: str = "backtest"
    dry_run: bool = True
    timeframe: str = "M5"
    poll_seconds: float = 5.0
    deviation: int = 20
    magic: int = 20250601


@dataclass
class TelegramConfig:
    bot_token: str = ""
    chat_id: str = ""


@dataclass
class NewsConfig:
    enabled: bool = True
    calendar_url: str = "https://nfs.faireconomy.com/ff_calendar_thisweek.xml"
    rss_feeds: list = None
    poll_seconds: int = 60
    blackout_minutes_before: int = 30
    blackout_minutes_after: int = 30
    blackout_impacts: list = None
    trade_news: bool = True
    news_window_minutes: int = 15
    news_surprise_threshold: float = 0.02
    news_sl_atr_mult: float = 2.0
    news_reward_risk: float = 2.0

    def __post_init__(self):
        if self.rss_feeds is None:
            self.rss_feeds = []
        if self.blackout_impacts is None:
            self.blackout_impacts = ["high", "medium"]


@dataclass
class Config:
    mt5: Mt5Config
    symbol: SymbolConfig
    strategy: StrategyConfig
    risk: RiskConfig
    execution: ExecutionConfig
    telegram: TelegramConfig
    news: NewsConfig
    initial_balance: float = 10000.0
    backtest_data: str = "data/EURUSD_M5.csv"
    state_path: str = "state/risk_state.json"
    kill_switch_path: str = "state/KILL_SWITCH"
    log_path: str = "logs/trades.jsonl"


def _section(raw, key, cls):
    data = raw.get(key) or {}
    names = {f.name for f in dataclasses.fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in names})


def load_config(path) -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config introuvable: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    mt5 = _section(raw, "mt5", Mt5Config)
    login_env = os.environ.get("MT5_LOGIN")
    if login_env:
        mt5.login = int(login_env)
    mt5.password = os.environ.get("MT5_PASSWORD", mt5.password)
    mt5.server = os.environ.get("MT5_SERVER", mt5.server)
    mt5.path = os.environ.get("MT5_PATH", mt5.path)

    telegram = _section(raw, "telegram", TelegramConfig)
    telegram.bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", telegram.bot_token)
    telegram.chat_id = os.environ.get("TELEGRAM_CHAT_ID", telegram.chat_id)

    cfg = Config(
        mt5=mt5,
        symbol=_section(raw, "symbol", SymbolConfig),
        strategy=_section(raw, "strategy", StrategyConfig),
        risk=_section(raw, "risk", RiskConfig),
        execution=_section(raw, "execution", ExecutionConfig),
        telegram=telegram,
        news=_section(raw, "news", NewsConfig),
        initial_balance=float(raw.get("initial_balance", 10000.0)),
        backtest_data=str(raw.get("backtest_data", "data/EURUSD_M5.csv")),
        state_path=str(raw.get("state_path", "state/risk_state.json")),
        kill_switch_path=str(raw.get("kill_switch_path", "state/KILL_SWITCH")),
        log_path=str(raw.get("log_path", "logs/trades.jsonl")),
    )

    if cfg.execution.mode not in ("backtest", "live"):
        raise ValueError("execution.mode doit être 'backtest' ou 'live'")
    if not cfg.symbol.name:
        raise ValueError("symbol.name est obligatoire")
    if cfg.symbol.pip_size <= 0 or cfg.symbol.contract_size <= 0:
        raise ValueError("pip_size et contract_size doivent être > 0")
    if cfg.risk.risk_per_trade_pct <= 0 or cfg.risk.risk_per_trade_pct > 10:
        raise ValueError("risk_per_trade_pct doit être dans ]0, 10]")
    if cfg.risk.max_daily_loss_pct <= 0 or cfg.risk.max_drawdown_pct <= 0:
        raise ValueError("Les limites de perte doivent être > 0")
    if cfg.strategy.fast_ema >= cfg.strategy.slow_ema:
        raise ValueError("fast_ema doit être < slow_ema")
    if cfg.news.news_surprise_threshold <= 0:
        raise ValueError("news_surprise_threshold doit être > 0")
    return cfg
