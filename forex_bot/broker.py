from abc import ABC, abstractmethod

from .models import AccountInfo, OrderResult, Position, Rate


class Broker(ABC):
    @abstractmethod
    def connect(self) -> bool:
        pass

    @abstractmethod
    def shutdown(self):
        pass

    @abstractmethod
    def account_info(self) -> AccountInfo:
        pass

    @abstractmethod
    def get_rates(self, symbol: str, timeframe: str, count: int) -> list:
        pass

    @abstractmethod
    def get_spread_pips(self, symbol: str) -> float:
        pass

    @abstractmethod
    def get_positions(self) -> list:
        pass

    @abstractmethod
    def market_order(self, symbol: str, volume: float, direction: str, sl: float, tp: float) -> OrderResult:
        pass

    @abstractmethod
    def close_position(self, ticket: int, price: float = None) -> OrderResult:
        pass

    @abstractmethod
    def close_all(self) -> int:
        pass

    @abstractmethod
    def get_closed_profit(self, ticket: int) -> float:
        pass
