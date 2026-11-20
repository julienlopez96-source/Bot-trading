from .broker import Broker
from .config import SymbolConfig
from .models import AccountInfo, OrderResult, Position, Rate


class PaperBroker(Broker):
    def __init__(self, symbol_cfg: SymbolConfig, balance: float = 10000.0):
        self.sym = symbol_cfg
        self.balance = float(balance)
        self.equity = float(balance)
        self.positions = []
        self.closed_trades = []
        self._closed_profit = {}
        self._next_ticket = 1
        self.rates = []

    def connect(self) -> bool:
        return True

    def shutdown(self):
        pass

    def update_rates(self, rates):
        if not rates:
            return
        self.rates = list(rates)
        self._check_stops(rates[-1])
        self._update_equity()

    def get_rates(self, symbol: str, timeframe: str, count: int) -> list:
        return self.rates[-count:]

    def get_spread_pips(self, symbol: str) -> float:
        return self.sym.spread_pips

    def account_info(self) -> AccountInfo:
        return AccountInfo(balance=self.balance, equity=self.equity, currency="USD")

    def get_positions(self) -> list:
        return list(self.positions)

    def market_order(self, symbol: str, volume: float, direction: str, sl: float, tp: float) -> OrderResult:
        if not self.rates:
            return OrderResult(False, error="pas de données de marché")
        close = self.rates[-1].close
        half_spread = self.sym.spread_pips * self.sym.pip_size / 2.0
        slippage = self.sym.slippage_pips * self.sym.pip_size
        if direction == "buy":
            price = close + half_spread + slippage
        else:
            price = close - half_spread - slippage
        pos = Position(
            ticket=self._next_ticket,
            symbol=symbol,
            direction=direction,
            volume=float(volume),
            open_price=price,
            sl=float(sl),
            tp=float(tp),
        )
        self._next_ticket += 1
        self.positions.append(pos)
        self._update_equity()
        return OrderResult(True, ticket=pos.ticket, price=price)

    def close_position(self, ticket: int, price: float = None) -> OrderResult:
        pos = next((p for p in self.positions if p.ticket == ticket), None)
        if pos is None:
            return OrderResult(False, error=f"position {ticket} introuvable")
        if price is None:
            close = self.rates[-1].close if self.rates else pos.open_price
            half_spread = self.sym.spread_pips * self.sym.pip_size / 2.0
            price = close - half_spread if pos.direction == "buy" else close + half_spread
        profit = self._profit(pos, price)
        self.positions.remove(pos)
        self.balance += profit
        self._closed_profit[ticket] = profit
        self.closed_trades.append(
            {"ticket": ticket, "symbol": pos.symbol, "direction": pos.direction, "profit": profit, "time": self.rates[-1].time if self.rates else 0}
        )
        self._update_equity()
        return OrderResult(True, ticket=ticket, price=price)

    def close_all(self) -> int:
        count = 0
        for pos in list(self.positions):
            if self.close_position(pos.ticket).success:
                count += 1
        return count

    def get_closed_profit(self, ticket: int) -> float:
        return self._closed_profit.get(ticket, 0.0)

    def _profit(self, pos: Position, price: float) -> float:
        diff = price - pos.open_price if pos.direction == "buy" else pos.open_price - price
        return diff * pos.volume * self.sym.contract_size

    def _floating(self) -> float:
        if not self.rates:
            return 0.0
        close = self.rates[-1].close
        return sum(self._profit(p, close) for p in self.positions)

    def _update_equity(self):
        self.equity = self.balance + self._floating()

    def _check_stops(self, bar: Rate):
        for pos in list(self.positions):
            if pos.direction == "buy":
                if bar.low <= pos.sl:
                    self.close_position(pos.ticket, price=pos.sl)
                elif bar.high >= pos.tp:
                    self.close_position(pos.ticket, price=pos.tp)
            else:
                if bar.high >= pos.sl:
                    self.close_position(pos.ticket, price=pos.sl)
                elif bar.low <= pos.tp:
                    self.close_position(pos.ticket, price=pos.tp)
