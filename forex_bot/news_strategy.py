import re

from .indicators import atr
from .models import NewsEvent, Rate, Signal


def parse_number(text: str):
    if not text:
        return None
    cleaned = text.replace(",", "").replace("%", "").strip()
    m = re.match(r"^([+-]?\d+(?:\.\d+)?)\s*([KMB])?$", cleaned, re.IGNORECASE)
    if not m:
        return None
    value = float(m.group(1))
    suffix = (m.group(2) or "").upper()
    if suffix == "K":
        value *= 1e3
    elif suffix == "M":
        value *= 1e6
    elif suffix == "B":
        value *= 1e9
    return value


BULLISH_WORDS = ["beat", "beats", "better", "stronger", "above expectations", "hawkish", "surge", "rally", "upbeat", "exceeds"]
BEARISH_WORDS = ["miss", "misses", "worse", "weaker", "below expectations", "dovish", "plunge", "slump", "downbeat", "falls short"]


class NewsStrategy:
    def __init__(self, cfg, symbol_cfg, atr_period: int):
        self.cfg = cfg
        self.sym = symbol_cfg
        self.base = symbol_cfg.name[:3].upper()
        self.quote = symbol_cfg.name[3:6].upper()
        self.atr_period = atr_period

    def on_event(self, event: NewsEvent, rates: list, now) -> Signal:
        c = self.cfg
        if not c.trade_news:
            return None
        if event.impact != "high" or not event.currency:
            return None
        if event.currency not in (self.base, self.quote):
            return None
        if event.time is None:
            return None
        delta = now.timestamp() - event.time
        if not (0 <= delta <= c.news_window_minutes * 60):
            return None
        event_direction = self._event_direction(event)
        if not event_direction:
            return None
        if event.currency == self.quote:
            direction = "sell" if event_direction == "bullish" else "buy"
        else:
            direction = "buy" if event_direction == "bullish" else "sell"
        atr_values = atr(rates, self.atr_period)
        if not atr_values or len(rates) < 2:
            return None
        entry = rates[-1].close
        sl_dist = atr_values[-1] * c.news_sl_atr_mult
        if direction == "buy":
            sl = entry - sl_dist
            tp = entry + sl_dist * c.news_reward_risk
        else:
            sl = entry + sl_dist
            tp = entry - sl_dist * c.news_reward_risk
        return Signal(symbol=self.sym.name, direction=direction, sl=sl, tp=tp, reason=f"news:{event.title[:40]}")

    def _event_direction(self, event: NewsEvent):
        actual = parse_number(event.actual)
        forecast = parse_number(event.forecast)
        if actual is not None and forecast is not None:
            diff = actual - forecast
            rel = diff / abs(forecast) if forecast != 0 else diff
            if rel >= self.cfg.news_surprise_threshold:
                return "bullish"
            if rel <= -self.cfg.news_surprise_threshold:
                return "bearish"
            return None
        title = event.title.lower()
        if any(w in title for w in BULLISH_WORDS):
            return "bullish"
        if any(w in title for w in BEARISH_WORDS):
            return "bearish"
        return None
