"""Balance-changing activities of one account, from the public NearBlocks API (no key needed).

Used for one check only: the gross flows of the buyback wallet. The main pipeline reads that wallet
as a net daily balance change (ft_balances_daily), which cannot show an outflow on a day with a
larger inflow, nor who sent the inflow. Each activity carries the balance after it, its direction
and the counterparty, so gross flows by counterparty can be rebuilt and checked against the net
series. Pages are requested newest first with the API's cursor, politely spaced.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx

from capture.extract.common import with_retries

BASE = "https://api.nearblocks.io/v1/account"
PER_PAGE = 100
DELAY_S = 11.0  # the free API allows a few requests a minute
KEEP = (
    "event_index",
    "block_height",
    "block_timestamp",
    "receipt_id",
    "transaction_hash",
    "involved_account_id",
    "direction",
    "cause",
    "absolute_nonstaked_amount",
)


class RateLimited(httpx.TransportError):
    pass


def fetch_activities(
    account: str,
    *,
    client: httpx.Client | None = None,
    delay: float = DELAY_S,
    sleep: Callable[[float], None] = time.sleep,
    max_pages: int = 200,
    on_page: Callable[[int, int], None] | None = None,
) -> list[dict]:
    """Every activity of `account`, oldest first, with only the fields the check needs."""
    own = client is None
    client = client or httpx.Client(timeout=60)
    rows: list[dict] = []
    cursor: str | None = None
    try:
        for page in range(max_pages):
            params = {"per_page": PER_PAGE, **({"cursor": cursor} if cursor else {})}

            def call(params: dict = params) -> dict:
                resp = client.get(f"{BASE}/{account}/activities", params=params)
                if resp.status_code == 429:
                    raise RateLimited("HTTP 429 from NearBlocks")
                resp.raise_for_status()
                return resp.json()

            if page:
                sleep(delay)
            payload = with_retries(call, base=delay, retry_on=(httpx.TransportError,))
            batch = payload.get("activities") or []
            seen = {r["event_index"] for r in rows}
            fresh = [{k: a.get(k) for k in KEEP} for a in batch if a["event_index"] not in seen]
            if batch and not fresh:  # the cursor did not move: stop instead of looping
                raise RuntimeError(
                    f"{account}: page {page + 1} repeats earlier rows (cursor stalled)"
                )
            rows += fresh
            if on_page:
                on_page(page + 1, len(rows))
            cursor = payload.get("cursor")
            if not batch or not cursor or len(batch) < PER_PAGE:
                break
        else:
            raise RuntimeError(f"{account}: more than {max_pages} pages; raise max_pages")
    finally:
        if own:
            client.close()
    unique = {r["event_index"]: r for r in rows}
    return sorted(unique.values(), key=lambda r: int(r["event_index"]))
