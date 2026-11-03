"""NEAR Intents Explorer API (1Click transactions), throttled and cached on disk.

Needs INTENTS_EXPLORER_JWT. Limit: 1 request per 5 seconds per partner. Every response is cached
under the cache directory, keyed by the request parameters, so re-runs never repeat a request.

Checked against the real API in F2 (DATA_AUDIT.md check 8): appFees[].fee is in basis points of
amountIn (official docs), and asset ids follow the patterns handled by chain_of().
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from pathlib import Path

import httpx
import pandas as pd

URL = "https://explorer.near-intents.org/api/v0/transactions"
PAGE_SIZE = 1000  # documented maximum
MAX_PAGES_PER_DAY = 200  # a day has ~20 pages; more means something is wrong
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
        hit = _read_cache(cached)
        if hit is not None:
            return hit
        for _ in range(self.retries_on_429 + 1):
            self._throttle()
            try:
                resp = self.http.get(URL, params=params, headers=self.headers)
            except httpx.TransportError:
                self.requests_made += 1
                continue  # timeout or dropped connection: ask again after another interval
            self.requests_made += 1
            if resp.status_code == 429:
                continue  # the next _throttle() waits another full interval
            resp.raise_for_status()
            data = _slim(resp.json())
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            tmp = cached.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8", newline="\n")
            os.replace(tmp, cached)  # a page is either whole or absent, even if the PC stops now
            return data
        raise RuntimeError("Explorer API kept answering 429 or timing out")

    def fetch_day(self, day: date) -> list[dict]:
        """All SUCCESS transactions created on `day` (UTC), newest first, without duplicates.

        Pages move backwards in time: the next request ends at the second of the last row of the
        previous page (the end bound is non-inclusive, so that second is requested again and the
        rows already seen are dropped). The API's cursor (lastDepositAddress) is not used: on
        2026-10-10 it returned the first page again after ten pages.
        """
        start = int(datetime.combine(day, dtime.min, tzinfo=UTC).timestamp()) - 1
        window_end = int(
            datetime.combine(day + timedelta(days=1), dtime.min, tzinfo=UTC).timestamp()
        )
        rows: list[dict] = []
        seen: set[tuple] = set()
        for _ in range(MAX_PAGES_PER_DAY):
            page = self.get(
                {
                    "numberOfTransactions": PAGE_SIZE,
                    "statuses": "SUCCESS",
                    "startTimestampUnix": start,
                    "endTimestampUnix": window_end,
                }
            )
            fresh = [tx for tx in page if _row_id(tx) not in seen]
            if page and not fresh:
                raise RuntimeError(f"{day}: a full page of already-seen rows; pagination is stuck")
            for tx in fresh:
                seen.add(_row_id(tx))
                rows.append(tx)
            if len(page) < PAGE_SIZE:
                return rows
            next_end = _seconds(page[-1]["createdAtTimestamp"]) + 1
            if next_end >= window_end:
                raise RuntimeError(f"{day}: {PAGE_SIZE} rows in one second; cannot page further")
            window_end = next_end
        raise RuntimeError(f"{day}: more than {MAX_PAGES_PER_DAY} pages; stopping")


def _read_cache(path: Path) -> list[dict] | None:
    """A cached page, or None if there is none or it is unreadable (cut short by a stop)."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        path.unlink(missing_ok=True)  # fetched again on the next request
        return None


# Fields the model uses. New cache files keep only these (about a fifth of the response size);
# cache files written earlier hold every field, which is a superset.
SLIM_FIELDS = (
    "depositAddress",
    "depositMemo",
    "createdAt",
    "createdAtTimestamp",
    "originAsset",
    "destinationAsset",
    "amountIn",
    "amountInUsd",
    "appFees",
    "referral",
    "status",
)


def _slim(transactions: list[dict]) -> list[dict]:
    return [{k: tx[k] for k in SLIM_FIELDS if k in tx} for tx in transactions]


def _row_id(tx: dict) -> tuple:
    return (
        tx["depositAddress"],
        tx.get("depositMemo"),
        tx["createdAt"],
        tx["originAsset"],
        tx["destinationAsset"],
        tx.get("amountIn"),
    )


def _seconds(timestamp: float) -> int:
    """createdAtTimestamp is in seconds; tolerate milliseconds."""
    return int(timestamp // 1000 if timestamp > 1e11 else timestamp)


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


NO_REFERRAL = "(none)"
NO_RECIPIENT = "(none)"
CHANNEL_COLUMNS = ["date", "referral", "volume_usd", "fee_usd", "tx_count"]
RECIPIENT_COLUMNS = ["date", "referral", "recipient", "volume_usd", "fee_usd", "tx_count"]


def _fees_by_recipient(tx: dict) -> dict[str, float]:
    """Declared app fee in USD per recipient (bps of amountIn; a recipient listed twice adds up)."""
    amount = float(tx.get("amountInUsd") or 0)
    out: dict[str, float] = defaultdict(float)
    for f in tx.get("appFees") or []:
        out[f["recipient"]] += amount * f["fee"] / 10_000
    return out


def aggregate_channels(day: date, transactions: list[dict]) -> list[dict]:
    """Group one day by channel = the transaction's referral ("(none)" when absent)."""
    groups: dict[str, dict] = defaultdict(
        lambda: {"volume_usd": 0.0, "fee_usd": 0.0, "tx_count": 0}
    )
    for tx in transactions:
        g = groups[tx.get("referral") or NO_REFERRAL]
        g["volume_usd"] += float(tx.get("amountInUsd") or 0)
        g["fee_usd"] += sum(_fees_by_recipient(tx).values())
        g["tx_count"] += 1
    return [{"date": day, "referral": ref, **g} for ref, g in sorted(groups.items())]


def aggregate_recipients(day: date, transactions: list[dict]) -> list[dict]:
    """Group one day by (referral, fee recipient). A transaction with several recipients counts in
    each of them, so volume_usd and tx_count are not additive across recipients. Transactions
    without any app fee are kept under the recipient "(none)"."""
    groups: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"volume_usd": 0.0, "fee_usd": 0.0, "tx_count": 0}
    )
    for tx in transactions:
        referral = tx.get("referral") or NO_REFERRAL
        amount = float(tx.get("amountInUsd") or 0)
        fees = _fees_by_recipient(tx) or {NO_RECIPIENT: 0.0}
        for recipient, fee_usd in fees.items():
            g = groups[(referral, recipient)]
            g["volume_usd"] += amount
            g["fee_usd"] += fee_usd
            g["tx_count"] += 1
    return [
        {"date": day, "referral": r, "recipient": rc, **g} for (r, rc), g in sorted(groups.items())
    ]


@dataclass
class ExplorerFrames:
    daily: pd.DataFrame  # explorer_1click_daily
    channels: pd.DataFrame  # explorer_channels_daily
    recipients: pd.DataFrame  # explorer_recipients_daily


def fetch_days(client: ExplorerClient, days: list[date]) -> ExplorerFrames:
    daily: list[dict] = []
    channels: list[dict] = []
    recipients: list[dict] = []
    for day in days:
        transactions = client.fetch_day(day)
        daily.extend(aggregate_day(day, transactions))
        channels.extend(aggregate_channels(day, transactions))
        recipients.extend(aggregate_recipients(day, transactions))
    return ExplorerFrames(
        pd.DataFrame(daily, columns=COLUMNS),
        pd.DataFrame(channels, columns=CHANNEL_COLUMNS),
        pd.DataFrame(recipients, columns=RECIPIENT_COLUMNS),
    )
