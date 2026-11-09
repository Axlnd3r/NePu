"""The NEAR Foundation revenue dashboard (revenue.near.org), kept as a labelled reference.

The page embeds a daily series `absoluteRevEmissions` with cumulative NEAR emissions and revenue
since 2026-01-01. Its footer says "Figures shown are illustrative", so the series is never mixed
into the measured data: it is stored as the page itself in data/reference/ and only read to show,
beside our own number, what the official dashboard publishes for the same day.
"""

from __future__ import annotations

import re

import httpx

URL = "https://revenue.near.org/"
_ROW = re.compile(
    r'\{"date":"(\d{4}-\d{2}-\d{2})","emissionsNear":([-\d.eE+]+),"revenueNear":([-\d.eE+]+)'
)


def fetch(client: httpx.Client | None = None) -> bytes:
    own = client is None
    client = client or httpx.Client(timeout=60, follow_redirects=True)
    try:
        resp = client.get(URL)
        resp.raise_for_status()
        return resp.content
    finally:
        if own:
            client.close()


def revenue_emissions(html: str) -> list[dict]:
    """Rows {date, emissions_near, revenue_near, revenue_share} of the embedded series."""
    text = html.replace('\\"', '"')
    start = text.find('"absoluteRevEmissions"')
    if start < 0:
        raise ValueError("absoluteRevEmissions not found in the page")
    rows = []
    for date, emissions, revenue in _ROW.findall(text[start : text.find("]", start)]):
        e, r = float(emissions), float(revenue)
        rows.append(
            {
                "date": date,
                "emissions_near": e,
                "revenue_near": r,
                "revenue_share": r / e if e else None,
            }
        )
    if not rows:
        raise ValueError("absoluteRevEmissions is empty")
    return rows


def on(rows: list[dict], date: str) -> dict:
    """The row for `date`, or the last one before it."""
    before = [r for r in rows if r["date"] <= date]
    if not before:
        raise ValueError(f"no official row on or before {date}")
    return before[-1]
