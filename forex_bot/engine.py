import time
from datetime import datetime

from .config import Config
from .risk import RiskManager
from .strategy import EmaAtrStrategy


class TradingEngine:
    def __init__(self, broker, strategy: EmaAtrStrategy, risk: RiskManager, cfg: Config, logger, notifier, dry_run: bool = True, news=None, news_strategy=None):
        self.broker = broker
        self.strategy = strategy
        self.risk = risk
        self.cfg = cfg
        self.logger = logger
        self.notifier = notifier
        self.dry_run = dry_run
        self.news = news
        self.news_strategy = news_strategy
        self.open_tickets = set()
        self._halt_reason = None
        self._blackout_logged = False

    def run(self):
        self.logger.log("engine_start", mode=self.cfg.execution.mode, dry_run=self.dry_run, symbol=self.cfg.symbol.name)
        self.notifier.send(f"Bot démarré ({self.cfg.symbol.name}, dry_run={self.dry_run})")
        while True:
            try:
                self.step(datetime.now())
            except Exception as e:
                self.logger.log("error", error=repr(e))
            time.sleep(self.cfg.execution.poll_seconds)

    def step(self, now: datetime):
        cfg = self.cfg
        symbol = cfg.symbol.name
        rates = self.broker.get_rates(symbol, cfg.execution.timeframe, cfg.strategy.lookback_bars)
        if not rates:
            self.logger.log("no_data", symbol=symbol)
            return

        acct = self.broker.account_info()
        positions = self.broker.get_positions()
        current = {p.ticket for p in positions}
        for ticket in list(self.open_tickets - current):
            profit = self.broker.get_closed_profit(ticket)
            self.risk.record_result(profit, now, acct.equity)
            self.logger.log("trade_closed", ticket=ticket, profit=round(profit, 2), equity=round(acct.equity, 2))
            self.notifier.send(f"Trade fermé ticket={ticket} profit={profit:.2f} {acct.currency}")
        self.open_tickets &= current

        if now.hour >= cfg.risk.force_close_hour and positions:
            closed = self.broker.close_all()
            self.logger.log("force_close_session", closed=closed)
            self.notifier.send(f"Clôture de fin de séance: {closed} position(s)")
            return

        ok, reason = self.risk.can_trade(now, acct.equity)
        if not ok:
            if reason != self._halt_reason:
                self._halt_reason = reason
                self.logger.log("halted", reason=reason, equity=round(acct.equity, 2))
                self.notifier.send(f"Bot en pause: {reason}")
            return
        if self._halt_reason:
            self._halt_reason = None
            self.logger.log("resumed")

        if len(positions) >= cfg.risk.max_open_positions:
            return

        spread = self.broker.get_spread_pips(symbol)
        signal = None
        if self.news is not None and self.cfg.news.enabled:
            self.news.update(now)
            if self.news.is_blackout(now):
                if not self._blackout_logged:
                    self._blackout_logged = True
                    self.logger.log("news_blackout", symbol=symbol)
                    self.notifier.send(f"Blackout news actif sur {symbol} : aucun nouvel ordre")
                return
            if self._blackout_logged:
                self._blackout_logged = False
                self.logger.log("news_blackout_over", symbol=symbol)
            if self.news_strategy is not None:
                for event in self.news.recent_events(now, self.cfg.news.news_window_minutes):
                    signal = self.news_strategy.on_event(event, rates, now)
                    if signal:
                        break
        if not signal:
            signal = self.strategy.on_rates(rates, {p.symbol for p in positions}, spread, now.hour)
        if not signal:
            return

        entry = rates[-1].close
        lots = self.risk.size_position(acct.balance, entry, signal.sl, cfg.symbol)
        if lots <= 0:
            self.logger.log("signal_rejected", reason="size_zero", direction=signal.direction, entry=entry)
            return

        if self.dry_run:
            self.logger.log("signal_dry_run", direction=signal.direction, lots=lots, entry=entry, sl=signal.sl, tp=signal.tp)
            self.notifier.send(f"[DRY-RUN] Signal {signal.direction} {lots} lots {symbol} @ {entry:.5f} SL={signal.sl:.5f} TP={signal.tp:.5f}")
            return

        result = self.broker.market_order(symbol, lots, signal.direction, signal.sl, signal.tp)
        self.logger.log(
            "order",
            success=result.success,
            ticket=result.ticket,
            direction=signal.direction,
            lots=lots,
            price=result.price,
            sl=signal.sl,
            tp=signal.tp,
            error=result.error,
        )
        if result.success:
            self.open_tickets.add(result.ticket)
            self.notifier.send(f"Ordre {signal.direction} exécuté: {lots} lots {symbol} @ {result.price:.5f}")
        else:
            self.notifier.send(f"Ordre refusé par le broker: {result.error}")
