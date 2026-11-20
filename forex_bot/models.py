from dataclasses import dataclass
from typing import Optional


@dataclass
class NewsEvent:
    title: str
    currency: str
    impact: str
    time: Optional[int] = None
    forecast: str = ""
    previous: str = ""
    actual: str = ""
    source: str = ""
    all_day: bool = False


@dataclass
class Rate:
    time: int
    open: float
    high: float
    low: float
    close: float
    tick_volume: int = 0


@dataclass
class Signal:
    symbol: str
    direction: str
    sl: float
    tp: float
    reason: str


@dataclass
class OrderResult:
    success: bool
    ticket: int = 0
    price: float = 0.0
    error: str = ""


@dataclass
class Position:
    ticket: int
    symbol: str
    direction: str
    volume: float
    open_price: float
    sl: float
    tp: float
    profit: float = 0.0


@dataclass
class AccountInfo:
    balance: float
    equity: float
    margin: float = 0.0
    currency: str = "USD"
