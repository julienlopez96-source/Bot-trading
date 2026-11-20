import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

from .models import NewsEvent

try:
    from zoneinfo import ZoneInfo
    NY_TZ = ZoneInfo("America/New_York")
except Exception:
    NY_TZ = timezone(timedelta(hours=-5))

USER_AGENT = "Mozilla/5.0 (compatible; forex-bot/1.0)"
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "CNY"]


def fetch_url(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def detect_currency(text: str) -> str:
    best = ""
    best_pos = len(text) + 1
    for c in CURRENCIES:
        m = re.search(rf"\b{c}\b", text)
        if m and m.start() < best_pos:
            best = c
            best_pos = m.start()
    return best


def parse_ff_datetime(date_str: str, time_str: str):
    date_str = (date_str or "").strip()
    time_str = (time_str or "").strip().lower()
    if not date_str:
        return None, False
    d = None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y"):
        try:
            d = datetime.strptime(date_str, fmt)
            break
        except ValueError:
            continue
    if d is None:
        return None, False
    if time_str in ("all day", "", "tentative"):
        dt = d.replace(hour=0, minute=0, tzinfo=NY_TZ)
        return int(dt.timestamp()), True
    m = re.match(r"(\d{1,2}):(\d{2})\s*(am|pm)", time_str)
    if not m:
        return None, False
    h = int(m.group(1)) % 12 + (12 if m.group(3) == "pm" else 0)
    dt = d.replace(hour=h, minute=int(m.group(2)), tzinfo=NY_TZ)
    return int(dt.timestamp()), False


class ForexFactoryCalendar:
    def __init__(self, url: str):
        self.url = url

    def fetch(self) -> list:
        root = ET.fromstring(fetch_url(self.url))
        events = []
        for node in root.iter("event"):
            title = (node.findtext("title") or "").strip()
            country = (node.findtext("country") or "").strip().upper()
            impact = (node.findtext("impact") or "").strip().lower()
            ts, all_day = parse_ff_datetime(node.findtext("date"), node.findtext("time"))
            events.append(
                NewsEvent(
                    title=title,
                    currency=country,
                    impact=impact,
                    time=ts,
                    forecast=(node.findtext("forecast") or "").strip(),
                    previous=(node.findtext("previous") or "").strip(),
                    actual=(node.findtext("actual") or "").strip(),
                    source="forexfactory",
                    all_day=all_day,
                )
            )
        return events


class RssFeed:
    def __init__(self, url: str, source: str = "rss"):
        self.url = url
        self.source = source

    def fetch(self) -> list:
        root = ET.fromstring(fetch_url(self.url))
        events = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            ts: Optional[int] = None
            if pub:
                try:
                    ts = int(parsedate_to_datetime(pub).timestamp())
                except Exception:
                    ts = None
            if ts is None:
                ts = int(datetime.now().timestamp())
            lowered = title.lower()
            impact = "high" if "high impact" in lowered else "news"
            events.append(
                NewsEvent(
                    title=title,
                    currency=detect_currency(title),
                    impact=impact,
                    time=ts,
                    source=self.source,
                )
            )
        return events


class NewsManager:
    def __init__(self, cfg, symbol_name: str, logger=None):
        self.cfg = cfg
        self.symbol = symbol_name
        self.base = symbol_name[:3].upper()
        self.quote = symbol_name[3:6].upper()
        self.logger = logger
        self.feeds = []
        if cfg.calendar_url:
            self.feeds.append(ForexFactoryCalendar(cfg.calendar_url))
        for url in cfg.rss_feeds:
            self.feeds.append(RssFeed(url))
        self.events = []
        self._last_fetch = 0.0

    def update(self, now: datetime) -> list:
        ts = now.timestamp()
        if ts - self._last_fetch < self.cfg.poll_seconds:
            return self.events
        self._last_fetch = ts
        events = []
        for feed in self.feeds:
            try:
                events.extend(feed.fetch())
            except Exception as e:
                if self.logger:
                    self.logger.log("news_feed_error", feed=type(feed).__name__, error=repr(e))
        self.events = events
        return events

    def _relevant(self, event: NewsEvent) -> bool:
        return event.currency in (self.base, self.quote)

    def is_blackout(self, now: datetime) -> bool:
        ts = now.timestamp()
        for e in self.events:
            if e.impact not in self.cfg.blackout_impacts or not self._relevant(e):
                continue
            if e.all_day and e.time is not None:
                day = datetime.fromtimestamp(e.time, tz=NY_TZ).date()
                if datetime.now(NY_TZ).date() == day:
                    return True
            if e.time is None:
                continue
            start = e.time - self.cfg.blackout_minutes_before * 60
            end = e.time + self.cfg.blackout_minutes_after * 60
            if start <= ts <= end:
                return True
        return False

    def recent_events(self, now: datetime, minutes: int) -> list:
        ts = now.timestamp()
        out = []
        for e in self.events:
            if e.time is None or not self._relevant(e):
                continue
            delta = ts - e.time
            if 0 <= delta <= minutes * 60:
                out.append(e)
        return sorted(out, key=lambda e: e.time, reverse=True)
