"""CoinGecko daily NEAR/USD price.

near_usd is the price at the first timestamp of each UTC day (00:00 UTC for both the hourly data
returned for ranges up to 90 days and the daily data returned for longer ranges).
The public API only serves the past 365 days (error 10012, DATA_AUDIT.md F2 notes) and caps the
span of one request, so long ranges are fetched in chunks.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime

import httpx
import pandas as pd

from capture.extract.common import with_retries

URL = "https://api.coingecko.com/api/v3/coins/near/market_chart/range"
MAX_SPAN_DAYS = 360  # the public API rejects ranges of more than 365 days
COLUMNS = ["date", "near_usd"]


def to_daily(prices: list[list[float]]) -> dict[date, float]:
    """First point of each UTC day. prices: [[unix_ms, usd], ...]."""
    out: dict[date, float] = {}
    for ts_ms, usd in sorted(prices):
        day = datetime.fromtimestamp(ts_ms / 1000, UTC).date()
        out.setdefault(day, float(usd))
    return out


def plan_requests(start: date, end: date) -> list[tuple[date, date]]:
    """Consecutive request ranges of at most MAX_SPAN_DAYS days covering [start, end]."""
    ranges = []
    cur = start
    while cur <= end:
        stop = min(end, cur + timedelta(days=MAX_SPAN_DAYS - 1))
        ranges.append((cur, stop))
        cur = stop + timedelta(days=1)
    return ranges


def _unix(day: date, end_of_day: bool = False) -> int:
    t = dtime(23, 59, 59) if end_of_day else dtime(0, 0, 0)
    return int(datetime.combine(day, t, tzinfo=UTC).timestamp())


def fetch_near_usd(
    start: date,
    end: date,
    api_key: str | None = None,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> pd.DataFrame:
    headers = {"x-cg-demo-api-key": api_key} if api_key else {}
    own = client is None
    client = client or httpx.Client(timeout=60, headers=headers)
    daily: dict[date, float] = {}
    try:
        for lo, hi in plan_requests(start, end):
            params = {"vs_currency": "usd", "from": _unix(lo), "to": _unix(hi, end_of_day=True)}

            def call(params: dict = params) -> dict:
                resp = client.get(URL, params=params)
                if resp.status_code in {429, 500, 502, 503, 504}:
                    raise httpx.TransportError(f"HTTP {resp.status_code} from CoinGecko")
                resp.raise_for_status()
                return resp.json()

            payload = with_retries(call, base=15.0, sleep=sleep, retry_on=(httpx.TransportError,))
            if "prices" not in payload:
                raise RuntimeError(f"CoinGecko response without prices: {str(payload)[:200]}")
            daily.update(to_daily(payload["prices"]))
            sleep(2.0)
    finally:
        if own:
            client.close()
    rows = [(d, p) for d, p in sorted(daily.items()) if start <= d <= end]
    return pd.DataFrame(rows, columns=COLUMNS)
