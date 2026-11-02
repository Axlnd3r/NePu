"""Paths, table registry and settings (from .env / environment)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
DATA_LIVE = ROOT / "data" / "live"
DATA_SNAPSHOT = ROOT / "data" / "snapshot"
SQL_DIR = ROOT / "sql"
DATASET = "bigquery-public-data.crypto_near_mainnet_us"

SETTING_KEYS = (
    "GOOGLE_CLOUD_PROJECT",
    "BQ_MAX_BYTES",
    "INTENTS_EXPLORER_JWT",
    "COINGECKO_API_KEY",
)

# Revenue wallets, see DATA_AUDIT.md check 4.
FEE_WALLETS = (
    "fefundsadmin.sputnik-dao.near",
    "1csfundsadmin.sputnik-dao.near",
    "buybacks.multisignature.near",
)

# Window start per table, see DATA_AUDIT.md "Gate 1 decision" and the F2 cost dry-runs.
ACTIVITY_START = date(
    2026, 4, 26
)  # buybacks.multisignature.near first appears in ft_balances_daily
SUPPLY_START = date(2025, 5, 10)  # start of DefiLlama fees/revenue history
FEE_WALLET_START = date(2025, 11, 7)  # fefundsadmin.sputnik-dao.near first appears
PRICE_START = SUPPLY_START
# The public CoinGecko API only serves the past 365 days; stay a couple of days inside it.
PRICE_PUBLIC_WINDOW_DAYS = 363

# DefiLlama days within this many days of today are not final (2026-10-31 was incomplete on 11-02).
DEFILLAMA_LAG_DAYS = 3


@dataclass(frozen=True)
class BqTable:
    name: str
    start: date
    key: tuple[str, ...]
    lag_days: int = 0  # extra days to hold back from the last complete day

    @property
    def sql_path(self) -> Path:
        return SQL_DIR / f"{self.name}.sql"

    @property
    def query_file(self) -> str:
        return f"sql/{self.name}.sql"


BQ_TABLES = {
    t.name: t
    for t in (
        BqTable("network_daily", ACTIVITY_START, ("date",)),
        BqTable("contracts_daily", ACTIVITY_START, ("date", "contract_account")),
        BqTable("intents_onchain_daily", ACTIVITY_START, ("date",)),
        BqTable("supply_daily", SUPPLY_START, ("date",)),
        # ft_balances_daily is partitioned by epoch_date and lands later than block tables.
        BqTable("fee_wallet_inflows_daily", FEE_WALLET_START, ("date", "wallet"), lag_days=1),
    )
}
API_TABLES = ("defillama_intents_daily", "price_daily", "explorer_1click_daily")
ALL_TABLES = (*BQ_TABLES, *API_TABLES)


def last_complete_day(today: date | None = None) -> date:
    return (today or datetime.now(UTC).date()) - timedelta(days=1)


def load_settings(env_path: Path = ROOT / ".env") -> dict[str, str]:
    """Values from .env, overridden by real environment variables. Empty values are dropped."""
    values = {k: v for k, v in dotenv_values(env_path).items() if v}
    for key in SETTING_KEYS:
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values
