"""DefiLlama daily series for NEAR Intents (no key needed).

One request per series returns the whole history, so this table is rebuilt on every run;
values that changed since the previous file are counted and reported (DefiLlama revises).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import httpx
import pandas as pd

from capture.extract.common import with_retries

BASE = "https://api.llama.fi"
# column -> (path, dataType)
SERIES = {
    "volume_usd": ("/summary/dexs/near-intents", None),
    "fees_usd": ("/summary/fees/near-intents", None),
    "revenue_usd": ("/summary/fees/near-intents", "dailyRevenue"),
    "holders_revenue_usd": ("/summary/fees/near-intents", "dailyHoldersRevenue"),
}
COLUMNS = ["date", *SERIES]
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def sources() -> str:
    urls = []
    for path, data_type in SERIES.values():
        urls.append(f"{BASE}{path}" + (f"?dataType={data_type}" if data_type else ""))
    return "; ".join(dict.fromkeys(urls))


def parse_chart(payload: dict) -> dict[date, float]:
    """totalDataChart is [[unix_ts_utc, value], ...] with one point per day."""
    return {
        datetime.fromtimestamp(ts, UTC).date(): float(value)
        for ts, value in payload["totalDataChart"]
        if value is not None
    }


def build_table(series: dict[str, dict[date, float]], last_final: date) -> pd.DataFrame:
    """Outer-join the series on date and drop days after last_final (not yet final)."""
    days = sorted({d for s in series.values() for d in s if d <= last_final})
    rows = [{"date": d, **{col: series[col].get(d) for col in SERIES}} for d in days]
    return pd.DataFrame(rows, columns=COLUMNS)


def count_revisions(old: pd.DataFrame | None, new: pd.DataFrame) -> int:
    """Number of (date, column) values in old that differ in new."""
    if old is None or old.empty:
        return 0
    merged = old.merge(new, on="date", suffixes=("_old", ""))
    changed = 0
    for col in SERIES:
        a, b = merged[f"{col}_old"], merged[col]
        changed += int((a.notna() & b.notna() & ((a - b).abs() > 1e-9)).sum())
    return changed


def _get(client: httpx.Client, path: str, data_type: str | None) -> dict:
    def call() -> dict:
        resp = client.get(f"{BASE}{path}", params={"dataType": data_type} if data_type else None)
        if resp.status_code in RETRYABLE_STATUS:
            raise httpx.TransportError(f"HTTP {resp.status_code} from {path}")
        resp.raise_for_status()
        return resp.json()

    return with_retries(call, retry_on=(httpx.TransportError,))


def fetch(
    lag_days: int, today: date | None = None, client: httpx.Client | None = None
) -> pd.DataFrame:
    today = today or datetime.now(UTC).date()
    last_final = today - timedelta(days=lag_days)
    own = client is None
    client = client or httpx.Client(timeout=60)
    try:
        series = {col: parse_chart(_get(client, path, dt)) for col, (path, dt) in SERIES.items()}
    finally:
        if own:
            client.close()
    return build_table(series, last_final)
