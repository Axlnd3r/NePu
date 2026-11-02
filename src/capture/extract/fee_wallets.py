"""Daily net change of the revenue wallets, derived from end-of-day balances.

Source: ft_balances_daily.liquid (NEAR units, FLOAT64). The result is the *net* change of each
wallet's balance, not gross inflow: outflows and transfers between wallets are not separated
(DATA_AUDIT.md check 4). The first observed day of a wallet has no previous balance, so its
change is unknown and left empty.
"""

from __future__ import annotations

import pandas as pd

DECIMALS = 24  # yoctoNEAR per NEAR
METHOD = "ft_balances_daily.liquid day-over-day change (float64)"
COLUMNS = [
    "date",
    "wallet",
    "token",
    "amount_raw",
    "decimals",
    "amount",
    "balance_end",
    "days_since_prev",
    "method",
]


def derive_inflows(balances: pd.DataFrame) -> pd.DataFrame:
    """balances: date, wallet, token, balance_end -> the fee_wallet_inflows_daily table."""
    df = balances[["date", "wallet", "token", "balance_end"]].copy()
    df = df.sort_values(["wallet", "date"]).reset_index(drop=True)
    prev_balance = df.groupby("wallet")["balance_end"].shift(1)
    prev_date = df.groupby("wallet")["date"].shift(1)
    df["amount"] = df["balance_end"] - prev_balance
    df["days_since_prev"] = [
        None if pd.isna(p) else (d - p).days for d, p in zip(df["date"], prev_date, strict=True)
    ]
    df["decimals"] = DECIMALS
    # amount_raw is derived from a float, so it is only accurate to ~15 significant digits.
    df["amount_raw"] = [None if pd.isna(a) else str(round(a * 10**DECIMALS)) for a in df["amount"]]
    df["method"] = METHOD
    return df[COLUMNS].sort_values(["date", "wallet"]).reset_index(drop=True)
