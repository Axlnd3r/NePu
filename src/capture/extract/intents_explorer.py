"""NEAR Intents Explorer API (1Click transactions), throttled and cached on disk.

Needs INTENTS_EXPLORER_JWT. Limit: 1 request per 5 seconds per partner. Every response is cached
under the cache directory, keyed by the request parameters, so re-runs never repeat a request.

Checked against the real API in F2 (DATA_AUDIT.md check 8): appFees[].fee is in basis points of
amountIn (official docs), and asset ids follow the patterns handled by chain_of().
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from pathlib import Path

import httpx
import pandas as pd

URL = "https://explorer.near-intents.org/api/v0/transactions"
PAGE_SIZE = 1000  # documented maximum
MIN_INTERVAL = 5.0
COLUMNS = [
    "date",
    "affiliate",
    "asset_in",
    "asset_out",
    "chain",
    "volume_usd",
    "fee_usd",
    "tx_count",
]


class ExplorerClient:
    def __init__(
        self,
        jwt: str,
        cache_dir: Path,
        *,
        http: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        min_interval: float = MIN_INTERVAL,
        retries_on_429: int = 5,
    ) -> None:
        self.cache_dir = cache_dir
        self.http = http or httpx.Client(timeout=60)
        self.headers = {"Authorization": f"Bearer {jwt}"}
        self.clock, self.sleep, self.min_interval = clock, sleep, min_interval
        self.retries_on_429 = retries_on_429
        self._last: float | None = None
        self.requests_made = 0

    def _throttle(self) -> None:
        if self._last is not None:
            wait = self._last + self.min_interval - self.clock()
            if wait > 0:
                self.sleep(wait)
        self._last = self.clock()

    def get(self, params: dict) -> list[dict]:
        key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
        cached = self.cache_dir / f"{key}.json"
        if cached.exists():
            return json.loads(cached.read_text(encoding="utf-8"))
        for _ in range(self.retries_on_429 + 1):
            self._throttle()
            resp = self.http.get(URL, params=params, headers=self.headers)
            self.requests_made += 1
            if resp.status_code == 429:
                continue  # the next _throttle() waits another full interval
            resp.raise_for_status()
            data = resp.json()
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cached.write_text(json.dumps(data), encoding="utf-8", newline="\n")
            return data
        raise RuntimeError("Explorer API kept answering 429")

    def fetch_day(self, day: date) -> list[dict]:
        """All SUCCESS transactions created on `day` (UTC). Both bounds are non-inclusive."""
        start = int(datetime.combine(day, dtime.min, tzinfo=UTC).timestamp()) - 1
        end = int(datetime.combine(day + timedelta(days=1), dtime.min, tzinfo=UTC).timestamp())
        params: dict = {
            "numberOfTransactions": PAGE_SIZE,
            "statuses": "SUCCESS",
            "startTimestampUnix": start,
            "endTimestampUnix": end,
        }
        rows: list[dict] = []
        while True:
            page = self.get(params)
            rows.extend(page)
            if len(page) < PAGE_SIZE:
                return rows
            last = page[-1]
            params = {**params, "lastDepositAddress": last["depositAddress"]}
            if last.get("depositMemo"):
                params["lastDepositMemo"] = last["depositMemo"]


def chain_of(asset_id: str) -> str:
    """Origin-chain label of an asset id, as encoded in the id (patterns seen in real data).

    nep141:<chain>-<address>.omft.near  -> <chain>   (eth, arb, base, tron, sol, gnosis, ...)
    nep141:<name>.omft.near             -> <name>    (native assets such as sol, xrp, zec)
    nep141:<anything else>              -> near      (token contract on NEAR, e.g. wrap.near)
    nep245:v2_1.omni.hot.tg:<id>_<addr> -> hot:<id>  (HOT omni id, left unmapped)
    1cs_v1:<chain>:<kind>:<id>          -> <chain>   (chain is written in the id)
    """
    standard, _, name = asset_id.partition(":")
    if standard == "nep141":
        if name.endswith(".omft.near"):
            return name.removesuffix(".omft.near").split("-", 1)[0]
        return "near"
    if standard == "nep245" and name.startswith("v2_1.omni.hot.tg:"):
        return "hot:" + name.split(":", 1)[1].split("_", 1)[0]
    if standard == "1cs_v1" and ":" in name:
        return name.split(":", 1)[0]
    return "unknown"


def aggregate_day(day: date, transactions: list[dict]) -> list[dict]:
    """Group one day of transactions by (affiliate, asset_in, asset_out, chain)."""
    groups: dict[tuple[str, str, str, str], dict] = defaultdict(
        lambda: {"volume_usd": 0.0, "fee_usd": 0.0, "tx_count": 0}
    )
    for tx in transactions:
        affiliate = ",".join(sorted({f["recipient"] for f in tx.get("appFees") or []}))
        asset_in, asset_out = tx["originAsset"], tx["destinationAsset"]
        g = groups[(affiliate, asset_in, asset_out, chain_of(asset_in))]
        amount_in_usd = float(tx.get("amountInUsd") or 0)
        fee_bps = sum(f["fee"] for f in tx.get("appFees") or [])
        g["volume_usd"] += amount_in_usd
        g["fee_usd"] += amount_in_usd * fee_bps / 10_000
        g["tx_count"] += 1
    return [
        {
            "date": day,
            "affiliate": aff,
            "asset_in": a_in,
            "asset_out": a_out,
            "chain": chain,
            "volume_usd": g["volume_usd"],
            # Requested app fee: amountInUsd x fee_bps / 10,000 summed over appFees. With a
            # partner key it is shared with 1Click (docs: resources/fees), so it is not what
            # the recipient nets.
            "fee_usd": g["fee_usd"],
            "tx_count": g["tx_count"],
        }
        for (aff, a_in, a_out, chain), g in sorted(groups.items())
    ]


def fetch_days(client: ExplorerClient, days: list[date]) -> pd.DataFrame:
    rows: list[dict] = []
    for day in days:
        rows.extend(aggregate_day(day, client.fetch_day(day)))
    return pd.DataFrame(rows, columns=COLUMNS)
