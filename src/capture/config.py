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

# Fixed seed for every random draw (permutation tests, Monte Carlo).
RANDOM_SEED = 20261114

# Valuation Lab (F5), see docs/METHODOLOGY.md. The two inflation rates are scenarios, not forecasts.
MC_PATHS = 10_000
MC_MONTHS = 60
MC_BLOCK_MONTHS = 3
GROWTH_START = date(2025, 6, 1)  # first month of the volume growth sample
DECAY_HALF_LIFE_MONTHS = 12
INFLATION_CURRENT = 0.025
INFLATION_PROPOSAL = 0.016
INFLATION_RAMP_MONTHS = 24
INFLATION_GRACE_MONTHS = 3  # HSP-029: 90-day grace period before the ramp

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
# First day with DefiLlama revenue above zero; the developer indicator is compared with it (F4).
CONTRACTS_START = date(2025, 9, 22)
# Explorer pull window start (F4: 4 months so that monthly views have more than one month).
EXPLORER_START = date(2026, 7, 1)
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
        BqTable("contracts_daily", CONTRACTS_START, ("date", "contract_account")),
        BqTable("intents_onchain_daily", ACTIVITY_START, ("date",)),
        BqTable("supply_daily", SUPPLY_START, ("date",)),
        # ft_balances_daily is partitioned by epoch_date and lands later than block tables.
        BqTable("fee_wallet_inflows_daily", FEE_WALLET_START, ("date", "wallet"), lag_days=1),
    )
}
EXPLORER_TABLES = ("explorer_1click_daily", "explorer_channels_daily", "explorer_recipients_daily")
API_TABLES = ("defillama_intents_daily", "price_daily", *EXPLORER_TABLES, "token_assets")
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
