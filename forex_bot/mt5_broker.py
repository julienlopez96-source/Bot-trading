from .broker import Broker
from .config import ExecutionConfig, Mt5Config, SymbolConfig
from .models import AccountInfo, OrderResult, Position, Rate

try:
    import MetaTrader5 as mt5
except Exception:
    mt5 = None


class MT5Broker(Broker):
    def __init__(self, mt5_cfg: Mt5Config, symbol_cfg: SymbolConfig, exec_cfg: ExecutionConfig):
        if mt5 is None:
            raise RuntimeError(
                "Le package MetaTrader5 n'est disponible que sous Windows avec le terminal MT5. "
                "Utilise le mode backtest (données CSV) sur les autres plateformes."
            )
        self.cfg = mt5_cfg
        self.symbol_cfg = symbol_cfg
        self.exec = exec_cfg
        self.timeframes = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
        }

    def connect(self) -> bool:
        if not mt5.initialize(
            login=self.cfg.login or None,
            password=self.cfg.password or None,
            server=self.cfg.server or None,
            path=self.cfg.path or None,
            timeout=self.cfg.timeout,
        ):
            if not mt5.initialize():
                return False
        return bool(mt5.symbol_select(self.symbol_cfg.name, True))

    def shutdown(self):
        mt5.shutdown()

    def account_info(self) -> AccountInfo:
        info = mt5.account_info()
        if info is None:
            return AccountInfo(balance=0.0, equity=0.0)
        return AccountInfo(
            balance=float(info.balance),
            equity=float(info.equity),
            margin=float(info.margin),
            currency=info.currency,
        )

    def get_rates(self, symbol: str, timeframe: str, count: int) -> list:
        tf = self.timeframes.get(timeframe)
        if tf is None:
            raise ValueError(f"Timeframe non supporté: {timeframe}")
        raw = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if raw is None:
            return []
        return [
            Rate(
                time=int(r["time"]),
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                tick_volume=int(r["tick_volume"]),
            )
            for r in raw
        ]

    def get_spread_pips(self, symbol: str) -> float:
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if tick is None or info is None:
            return 0.0
        return tick.spread * info.point / self.symbol_cfg.pip_size

    def get_positions(self) -> list:
        raw = mt5.positions_get(magic=self.exec.magic)
        if raw is None:
            return []
        out = []
        for p in raw:
            direction = "buy" if p.type == mt5.ORDER_TYPE_BUY else "sell"
            out.append(
                Position(
                    ticket=int(p.ticket),
                    symbol=p.symbol,
                    direction=direction,
                    volume=float(p.volume),
                    open_price=float(p.price_open),
                    sl=float(p.sl),
                    tp=float(p.tp),
                    profit=float(p.profit),
                )
            )
        return out

    def market_order(self, symbol: str, volume: float, direction: str, sl: float, tp: float) -> OrderResult:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return OrderResult(False, error="pas de tick")
        is_buy = direction == "buy"
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
            "price": tick.ask if is_buy else tick.bid,
            "sl": float(sl),
            "tp": float(tp),
            "deviation": self.exec.deviation,
            "magic": self.exec.magic,
            "comment": "forex-bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(request)
        if res is None:
            return OrderResult(False, error="order_send a retourné None")
        if res.retcode != mt5.TRADE_RETCODE_DONE:
            return OrderResult(False, error=f"retcode={res.retcode} {res.comment}")
        return OrderResult(True, ticket=int(res.order), price=float(res.price))

    def close_position(self, ticket: int, price: float = None) -> OrderResult:
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return OrderResult(False, error=f"position {ticket} introuvable")
        pos = positions[0]
        tick = mt5.symbol_info_tick(pos.symbol)
        is_buy_pos = pos.type == mt5.ORDER_TYPE_BUY
        if price is None:
            price = tick.bid if is_buy_pos else tick.ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": int(pos.ticket),
            "symbol": pos.symbol,
            "volume": float(pos.volume),
            "type": mt5.ORDER_TYPE_SELL if is_buy_pos else mt5.ORDER_TYPE_BUY,
            "price": float(price),
            "deviation": self.exec.deviation,
            "magic": self.exec.magic,
            "comment": "forex-bot-close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(request)
        if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
            code = res.retcode if res is not None else "None"
            return OrderResult(False, error=f"retcode={code}")
        return OrderResult(True, ticket=int(pos.ticket), price=float(res.price))

    def close_all(self) -> int:
        count = 0
        for pos in self.get_positions():
            if self.close_position(pos.ticket).success:
                count += 1
        return count

    def get_closed_profit(self, ticket: int) -> float:
        deals = mt5.history_deals_get(position=ticket)
        if deals is None:
            return 0.0
        return float(sum(d.profit for d in deals))
