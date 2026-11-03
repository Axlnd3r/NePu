"""Asset metadata from the public 1Click token list (no key needed).

Maps Explorer asset ids to a symbol and blockchain so that ZEC and stablecoins can be recognised.
Only identifiers are kept; the list's prices are not stored. The table is a snapshot of the list
at pull time and has no date column.
"""

from __future__ import annotations

import httpx
import pandas as pd

from capture.extract.common import with_retries

URL = "https://1click.chaindefuser.com/v0/tokens"
COLUMNS = ["asset_id", "symbol", "blockchain", "decimals"]
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def to_frame(payload: list[dict]) -> pd.DataFrame:
    rows = [
        {
            "asset_id": t["assetId"],
            "symbol": t["symbol"],
            "blockchain": t["blockchain"],
            "decimals": t["decimals"],
        }
        for t in payload
    ]
    frame = pd.DataFrame(rows, columns=COLUMNS)
    return frame.drop_duplicates("asset_id").sort_values("asset_id").reset_index(drop=True)


def fetch(client: httpx.Client | None = None) -> pd.DataFrame:
    own = client is None
    client = client or httpx.Client(timeout=60)

    def call() -> list[dict]:
        resp = client.get(URL)
        if resp.status_code in RETRYABLE_STATUS:
            raise httpx.TransportError(f"HTTP {resp.status_code} from {URL}")
        resp.raise_for_status()
        return resp.json()

    try:
        return to_frame(with_retries(call, retry_on=(httpx.TransportError,)))
    finally:
        if own:
            client.close()
