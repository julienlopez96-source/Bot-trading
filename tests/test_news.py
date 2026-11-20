import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forex_bot.config import NewsConfig, SymbolConfig
from forex_bot.models import NewsEvent, Rate
from forex_bot.news import NewsManager, detect_currency, parse_ff_datetime
from forex_bot.news_strategy import NewsStrategy, parse_number

NY = ZoneInfo("America/New_York")

FF_XML = """<?xml version="1.0"?>
<weeklyevents>
  <event>
    <title>Non-Farm Payrolls</title>
    <country>USD</country>
    <date>2025-01-10</date>
    <time>8:30am</time>
    <impact>High</impact>
    <forecast>150K</forecast>
    <previous>180K</previous>
    <actual>250K</actual>
  </event>
  <event>
    <title>Eurozone GDP q/q</title>
    <country>EUR</country>
    <date>2025-01-10</date>
    <time>all day</time>
    <impact>Medium</impact>
    <forecast>0.2%</forecast>
    <previous>0.1%</previous>
  </event>
</weeklyevents>
"""

RSS_XML = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>Fed signals hawkish stance, USD rallies</title>
    <pubDate>Fri, 10 Jan 2025 13:45:00 +0000</pubDate>
  </item>
  <item>
    <title>Oil prices steady</title>
    <pubDate>Fri, 10 Jan 2025 12:00:00 +0000</pubDate>
  </item>
</channel></rss>
"""


def make_news_cfg(**overrides):
    params = dict(enabled=True, calendar_url="", rss_feeds=[], poll_seconds=60,
                  blackout_minutes_before=30, blackout_minutes_after=30,
                  blackout_impacts=["high", "medium"], trade_news=True,
                  news_window_minutes=15, news_surprise_threshold=0.02,
                  news_sl_atr_mult=2.0, news_reward_risk=2.0)
    params.update(overrides)
    return NewsConfig(**params)


def make_symbol():
    return SymbolConfig(name="EURUSD", pip_size=0.0001, contract_size=100000.0,
                        spread_pips=1.5, slippage_pips=0.5)


def make_rates(n=30, base=1.10):
    rates = []
    for i in range(n):
        c = base + 0.0001 * i
        rates.append(Rate(time=i * 300, open=c, high=c + 0.0005, low=c - 0.0005, close=c, tick_volume=100))
    return rates


class TestParsing(unittest.TestCase):
    def test_parse_ff_datetime(self):
        ts, all_day = parse_ff_datetime("2025-01-10", "8:30am")
        expected = int(datetime(2025, 1, 10, 8, 30, tzinfo=NY).timestamp())
        self.assertEqual(ts, expected)
        self.assertFalse(all_day)

    def test_parse_ff_datetime_all_day(self):
        ts, all_day = parse_ff_datetime("2025-01-10", "all day")
        self.assertTrue(all_day)
        self.assertIsNotNone(ts)

    def test_parse_ff_datetime_pm(self):
        ts, _ = parse_ff_datetime("2025-01-10", "1:30pm")
        expected = int(datetime(2025, 1, 10, 13, 30, tzinfo=NY).timestamp())
        self.assertEqual(ts, expected)

    def test_parse_number(self):
        self.assertEqual(parse_number("250K"), 250000.0)
        self.assertEqual(parse_number("0.3%"), 0.3)
        self.assertEqual(parse_number("1,234.5"), 1234.5)
        self.assertEqual(parse_number("2M"), 2000000.0)
        self.assertIsNone(parse_number(""))
        self.assertIsNone(parse_number("n/a"))

    def test_detect_currency(self):
        self.assertEqual(detect_currency("USD rallies higher"), "USD")
        self.assertEqual(detect_currency("EUR/USD steady"), "EUR")
        self.assertEqual(detect_currency("Oil steady"), "")


class TestNewsManager(unittest.TestCase):
    def test_blackout_window(self):
        cfg = make_news_cfg()
        mgr = NewsManager(cfg, "EURUSD")
        t = int(datetime(2025, 1, 10, 8, 30, tzinfo=NY).timestamp())
        mgr.events = [NewsEvent(title="NFP", currency="USD", impact="high", time=t)]
        now = datetime.fromtimestamp(t - 10 * 60, tz=timezone.utc)
        self.assertTrue(mgr.is_blackout(now))
        now = datetime.fromtimestamp(t + 10 * 60, tz=timezone.utc)
        self.assertTrue(mgr.is_blackout(now))
        now = datetime.fromtimestamp(t + 60 * 60, tz=timezone.utc)
        self.assertFalse(mgr.is_blackout(now))

    def test_blackout_ignores_other_currencies_and_low_impact(self):
        cfg = make_news_cfg()
        mgr = NewsManager(cfg, "EURUSD")
        t = int(datetime(2025, 1, 10, 8, 30, tzinfo=NY).timestamp())
        mgr.events = [
            NewsEvent(title="JPY news", currency="JPY", impact="high", time=t),
            NewsEvent(title="US minor", currency="USD", impact="low", time=t),
        ]
        now = datetime.fromtimestamp(t, tz=timezone.utc)
        self.assertFalse(mgr.is_blackout(now))

    def test_blackout_medium_in_impacts(self):
        cfg = make_news_cfg()
        mgr = NewsManager(cfg, "EURUSD")
        t = int(datetime(2025, 1, 10, 8, 30, tzinfo=NY).timestamp())
        mgr.events = [NewsEvent(title="CPI", currency="USD", impact="medium", time=t)]
        now = datetime.fromtimestamp(t, tz=timezone.utc)
        self.assertTrue(mgr.is_blackout(now))

    def test_recent_events_window(self):
        cfg = make_news_cfg()
        mgr = NewsManager(cfg, "EURUSD")
        t = int(datetime(2025, 1, 10, 8, 30, tzinfo=NY).timestamp())
        mgr.events = [
            NewsEvent(title="NFP", currency="USD", impact="high", time=t),
            NewsEvent(title="old", currency="USD", impact="high", time=t - 3600),
            NewsEvent(title="future", currency="USD", impact="high", time=t + 3600),
            NewsEvent(title="other ccy", currency="JPY", impact="high", time=t - 60),
        ]
        now = datetime.fromtimestamp(t + 5 * 60, tz=timezone.utc)
        recent = mgr.recent_events(now, 15)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0].title, "NFP")


class TestNewsStrategy(unittest.TestCase):
    def setUp(self):
        self.cfg = make_news_cfg()
        self.strategy = NewsStrategy(self.cfg, make_symbol(), atr_period=14)
        self.t = int(datetime(2025, 1, 10, 8, 30, tzinfo=NY).timestamp())

    def test_usd_beat_gives_sell_on_eurusd(self):
        event = NewsEvent(title="NFP", currency="USD", impact="high", time=self.t, forecast="150K", actual="250K")
        now = datetime.fromtimestamp(self.t + 5 * 60, tz=timezone.utc)
        signal = self.strategy.on_event(event, make_rates(), now)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "sell")
        self.assertGreater(signal.sl, 1.1029)
        self.assertLess(signal.tp, 1.1029)

    def test_base_currency_beat_gives_buy(self):
        event = NewsEvent(title="ECB", currency="EUR", impact="high", time=self.t, forecast="2.0%", actual="2.5%")
        now = datetime.fromtimestamp(self.t + 5 * 60, tz=timezone.utc)
        signal = self.strategy.on_event(event, make_rates(), now)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "buy")

    def test_usd_miss_gives_buy_on_eurusd(self):
        event = NewsEvent(title="NFP", currency="USD", impact="high", time=self.t, forecast="150K", actual="80K")
        now = datetime.fromtimestamp(self.t + 5 * 60, tz=timezone.utc)
        signal = self.strategy.on_event(event, make_rates(), now)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "buy")

    def test_no_signal_outside_window(self):
        event = NewsEvent(title="NFP", currency="USD", impact="high", time=self.t, forecast="150K", actual="250K")
        now = datetime.fromtimestamp(self.t + 30 * 60, tz=timezone.utc)
        self.assertIsNone(self.strategy.on_event(event, make_rates(), now))

    def test_no_signal_when_surprise_too_small(self):
        event = NewsEvent(title="CPI", currency="USD", impact="high", time=self.t, forecast="3.0%", actual="3.01%")
        now = datetime.fromtimestamp(self.t + 5 * 60, tz=timezone.utc)
        self.assertIsNone(self.strategy.on_event(event, make_rates(), now))

    def test_no_signal_low_impact(self):
        event = NewsEvent(title="minor", currency="USD", impact="low", time=self.t, forecast="1", actual="5")
        now = datetime.fromtimestamp(self.t + 5 * 60, tz=timezone.utc)
        self.assertIsNone(self.strategy.on_event(event, make_rates(), now))

    def test_no_signal_without_actual(self):
        event = NewsEvent(title="NFP", currency="USD", impact="high", time=self.t, forecast="150K", actual="")
        now = datetime.fromtimestamp(self.t + 5 * 60, tz=timezone.utc)
        self.assertIsNone(self.strategy.on_event(event, make_rates(), now))

    def test_keyword_fallback_direction(self):
        event = NewsEvent(title="Fed Beige Book beats expectations", currency="USD", impact="high", time=self.t)
        now = datetime.fromtimestamp(self.t + 5 * 60, tz=timezone.utc)
        signal = self.strategy.on_event(event, make_rates(), now)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "sell")

    def test_trade_news_disabled(self):
        cfg = make_news_cfg(trade_news=False)
        strategy = NewsStrategy(cfg, make_symbol(), atr_period=14)
        event = NewsEvent(title="NFP", currency="USD", impact="high", time=self.t, forecast="150K", actual="250K")
        now = datetime.fromtimestamp(self.t + 5 * 60, tz=timezone.utc)
        self.assertIsNone(strategy.on_event(event, make_rates(), now))


if __name__ == "__main__":
    unittest.main()
