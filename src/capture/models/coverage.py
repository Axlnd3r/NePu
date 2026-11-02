"""Coverage-ratio model: pure functions over the snapshot tables (see docs/METHODOLOGY.md).

All series are daily and indexed by pandas Timestamps at UTC midnight. Rolling windows require a
complete window of inputs (min_periods == window), so a missing input gives an empty value rather
than a silently shorter average.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

WINDOWS = (7, 30, 90)
# Largest accepted gap between on-chain and DefiLlama monthly revenue (docs/METHODOLOGY.md).
RECONCILIATION_TOLERANCE = 0.15
BUYBACK_WALLET = "buybacks.multisignature.near"
WALLET_SHORT = {
    "buybacks.multisignature.near": "buybacks",
    "fefundsadmin.sputnik-dao.near": "fefundsadmin",
    "1csfundsadmin.sputnik-dao.near": "1csfundsadmin",
}
# A fall of at least this many NEAR in a revenue wallet counts as a possible transfer out of it.
TRANSFER_MIN_NEAR = 1.0
SUPPLY_COLUMNS = ["total_supply_near", "burnt_near"]
DEFILLAMA_COLUMNS = ["volume_usd", "fees_usd", "revenue_usd", "holders_revenue_usd"]


def _daily(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.assign(date=pd.to_datetime(df["date"])).set_index("date")[columns]
    if not out.index.is_unique:
        raise ValueError("duplicate dates in input table")
    return out.sort_index()


def wallet_changes(fee_wallet_inflows: pd.DataFrame) -> pd.DataFrame:
    """One column chg_<wallet> per revenue wallet: net daily change of its balance, in NEAR."""
    df = fee_wallet_inflows.assign(date=pd.to_datetime(fee_wallet_inflows["date"]))
    piv = df.pivot(index="date", columns="wallet", values="amount")
    piv = piv.rename(columns={w: f"chg_{WALLET_SHORT[w]}" for w in piv.columns})
    return piv.sort_index()


def build_inputs(tables: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """Join the snapshot tables into one daily frame (the model's only input)."""
    supply = _daily(tables["supply_daily"], SUPPLY_COLUMNS)
    price = _daily(tables["price_daily"], ["near_usd"])
    llama = _daily(tables["defillama_intents_daily"], DEFILLAMA_COLUMNS)
    wallets = wallet_changes(tables["fee_wallet_inflows_daily"])
    index = pd.date_range(supply.index.min(), supply.index.max(), freq="D")
    frame = pd.DataFrame(index=index)
    for part in (supply, price, llama, wallets):
        frame = frame.join(part)
    frame.index.name = "date"
    return frame


def issuance_gross_near(total_supply_near: pd.Series, burnt_near: pd.Series) -> pd.Series:
    """total_supply(d) - total_supply(d-1) + burnt_near(d): NEAR minted on day d."""
    return total_supply_near.diff() + burnt_near


def internal_transfers_in(
    changes: pd.DataFrame, target: str = "chg_buybacks", min_near: float = TRANSFER_MIN_NEAR
) -> pd.Series:
    """Estimated NEAR that reached `target` from the other revenue wallets on each day.

    When another revenue wallet falls by at least min_near and the target rises on the same day,
    the transfer is taken as the smaller of the two moves. A fall of the target itself is never a
    transfer in. Validated against receipts in docs/audit/internal_transfers_validation.json.
    """
    others = changes.drop(columns=[target], errors="ignore")
    falls = (-others).where(others <= -min_near, 0.0).clip(lower=0.0).fillna(0.0)
    rise = changes[target].clip(lower=0.0)
    return pd.concat([falls.sum(axis=1), rise], axis=1).min(axis=1).where(rise.notna())


def buyback_near(changes: pd.DataFrame, target: str = "chg_buybacks") -> pd.Series:
    """NEAR received by the buyback wallet from outside the revenue wallets.

    Positive part of the wallet's daily net change, minus estimated transfers from the other
    revenue wallets. Outflows are ignored (nothing is "un-bought"). Empty on the wallet's first
    observed day and before it existed.
    """
    received = changes[target].clip(lower=0.0)
    return (received - internal_transfers_in(changes, target)).clip(lower=0.0)


def buyback_near_proxy(holders_revenue_usd: pd.Series, near_usd: pd.Series) -> pd.Series:
    """DefiLlama holders revenue converted at the day's price. A proxy, not a measurement:
    it equals total captured revenue, including wallets that only hold."""
    return holders_revenue_usd / near_usd


def fill_source_gaps(changes: pd.DataFrame) -> pd.DataFrame:
    """Set days missing inside a wallet's observed span to 0.

    When the source skips days, the first change after the gap already covers all of them (see
    days_since_prev in fee_wallet_inflows_daily), so the sum over the gap is preserved. Days
    before a wallet's first or after its last observation stay empty.
    """
    out = changes.copy()
    for col in out.columns:
        first, last = out[col].first_valid_index(), out[col].last_valid_index()
        if first is None:
            continue
        interior = (out.index > first) & (out.index < last)
        out.loc[interior & out[col].isna(), col] = 0.0
    return out


def onchain_revenue_near(changes: pd.DataFrame) -> pd.Series:
    """NEAR that entered the revenue wallets from outside them (all wallets, transfers netted).

    Empty only on days when no wallet has data. A wallet that does not exist yet contributes 0.
    """
    filled = fill_source_gaps(changes)
    rises = filled.clip(lower=0.0).sum(axis=1, min_count=1)
    transfers = internal_transfers_in(filled).fillna(0.0)
    return (rises - transfers).clip(lower=0.0).where(rises.notna())


def rolling_sum(s: pd.Series, window: int) -> pd.Series:
    return s.rolling(window, min_periods=window).sum()


def _ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    return (num / den).where(den > 0)


def cr_float(buyback: pd.Series, burnt: pd.Series, issuance: pd.Series, window: int) -> pd.Series:
    """sum(buyback + burn) / sum(gross issuance) over the window, all in NEAR."""
    return _ratio(rolling_sum(buyback + burnt, window), rolling_sum(issuance, window))


def cr_supply(burnt: pd.Series, issuance: pd.Series, window: int) -> pd.Series:
    """sum(burn) / sum(gross issuance): buybacks do not reduce total supply."""
    return _ratio(rolling_sum(burnt, window), rolling_sum(issuance, window))


def cr_float_usd(
    buyback: pd.Series,
    burnt: pd.Series,
    issuance: pd.Series,
    near_usd: pd.Series,
    window: int,
) -> pd.Series:
    """CR_float with every day valued at that day's price."""
    num = rolling_sum((buyback + burnt) * near_usd, window)
    return _ratio(num, rolling_sum(issuance * near_usd, window))


def tau_eff(revenue_usd: pd.Series, volume_usd: pd.Series, window: int) -> pd.Series:
    """sum(revenue) / sum(volume). Empty where the window has no revenue (not zero)."""
    revenue_sum = rolling_sum(revenue_usd, window)
    return _ratio(revenue_sum.where(revenue_sum > 0), rolling_sum(volume_usd, window))


def coverage_table(inputs: pd.DataFrame, windows: tuple[int, ...] = WINDOWS) -> pd.DataFrame:
    """Every daily series of the model, one column each, from build_inputs() output."""
    changes = inputs[[c for c in inputs.columns if c.startswith("chg_")]]
    issuance = issuance_gross_near(inputs["total_supply_near"], inputs["burnt_near"])
    burnt = inputs["burnt_near"]
    price = inputs["near_usd"]
    bb = buyback_near(changes)
    proxy = buyback_near_proxy(inputs["holders_revenue_usd"], price)
    out = pd.DataFrame(
        {
            "total_supply_near": inputs["total_supply_near"],
            "issuance_gross_near": issuance,
            "burnt_near": burnt,
            "buyback_near": bb,
            "buyback_near_proxy": proxy,
            "near_usd": price,
        }
    )
    for w in windows:
        out[f"cr_float_{w}"] = cr_float(bb, burnt, issuance, w)
        out[f"cr_supply_{w}"] = cr_supply(burnt, issuance, w)
        out[f"cr_float_usd_{w}"] = cr_float_usd(bb, burnt, issuance, price, w)
        out[f"cr_float_proxy_{w}"] = cr_float(proxy, burnt, issuance, w)
        out[f"tau_eff_{w}"] = tau_eff(inputs["revenue_usd"], inputs["volume_usd"], w)
    return out


def monthly_reconciliation(inputs: pd.DataFrame) -> pd.DataFrame:
    """On-chain revenue (wallet inflows x daily price) vs DefiLlama revenue, complete months only.

    A month is included only if every day has a price, a DefiLlama revenue and a wallet change.
    deviation = on-chain / DefiLlama - 1.
    """
    changes = inputs[[c for c in inputs.columns if c.startswith("chg_")]]
    onchain_near = onchain_revenue_near(changes)
    frame = pd.DataFrame(
        {
            "onchain_usd": onchain_near * inputs["near_usd"],
            "defillama_usd": inputs["revenue_usd"],
        }
    )
    complete = frame.notna().all(axis=1)
    frame = frame[complete]
    grouped = frame.groupby(frame.index.to_period("M"))
    out = grouped.sum().assign(days=grouped.size())
    expected = out.index.map(lambda p: p.days_in_month)
    out = out[out["days"] == expected].drop(columns="days")
    out["deviation"] = out["onchain_usd"] / out["defillama_usd"] - 1
    out["within_tolerance"] = out["deviation"].abs() <= RECONCILIATION_TOLERANCE
    out.index = out.index.astype(str)
    out.index.name = "month"
    return out
