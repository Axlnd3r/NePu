"""Distribution Map: who brings Intents volume and fees, and how concentrated it is.

Pure functions over the snapshot tables (see docs/METHODOLOGY.md). Scope: the Explorer API only
covers 1Click transactions, so every Explorer-based number describes that part of Intents.

Periods are calendar months ("month") or weeks starting on Monday ("week"). A period is
`complete` only if every day of it lies inside the Explorer date range.
"""

from __future__ import annotations

import pandas as pd

from capture.models.coverage import WALLET_SHORT

NEAR_WALLETS = frozenset(WALLET_SHORT)
TOP_N = 5
NO_REFERRAL = "(none)"
UNMAPPED = "(unmapped)"
ZEC_SYMBOL = "ZEC"
# USD-pegged tokens in the 1Click token list. A judgment call, listed in distribution.json.
# Yield-bearing vault shares (sUSDC, steakUSDC, ...) and EUR/GBP tokens are not included.
STABLECOIN_SYMBOLS = frozenset(
    {"USDT", "USDC", "DAI", "USDT0", "USDT0(DEPRECATED)", "USD1", "USDG", "USDe", "USDf", "FRAX"}
    | {"USAD", "USDCx", "xDAI"}
)


def period_of(dates: pd.Series, freq: str) -> pd.Series:
    """Label of the period each date falls in: 'YYYY-MM' or the ISO date of the week's Monday."""
    d = pd.to_datetime(dates)
    if freq == "month":
        return d.dt.to_period("M").astype(str)
    if freq == "week":
        return (d - pd.to_timedelta(d.dt.day_of_week, unit="D")).dt.strftime("%Y-%m-%d")
    raise ValueError(f"unknown frequency {freq!r}")


def period_bounds(period: str, freq: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    if freq == "month":
        p = pd.Period(period, "M")
        return p.start_time.normalize(), p.end_time.normalize()
    start = pd.Timestamp(period)
    return start, start + pd.Timedelta(days=6)


def period_table(periods: list[str], freq: str, first: object, last: object) -> pd.DataFrame:
    """For each period: days inside [first, last], and whether that is every day of the period."""
    lo, hi = pd.Timestamp(first), pd.Timestamp(last)
    rows = []
    for period in sorted(set(periods)):
        start, end = period_bounds(period, freq)
        covered = (min(end, hi) - max(start, lo)).days + 1
        full = (end - start).days + 1
        rows.append({"period": period, "days": max(covered, 0), "complete": covered == full})
    return pd.DataFrame(rows, columns=["period", "days", "complete"])


def hhi(shares: pd.Series) -> float:
    """Herfindahl-Hirschman index: the sum of squared shares, in [1/n, 1] for n entries."""
    return float((shares**2).sum())


def top_share(shares: pd.Series, n: int = TOP_N) -> float:
    return float(shares.nlargest(n).sum())


def volume_shares(frame: pd.DataFrame, key: str, freq: str) -> pd.DataFrame:
    """Volume, fee, transaction count and share of the period's volume per `key`, per period."""
    grouped = (
        frame.assign(period=period_of(frame["date"], freq))
        .groupby(["period", key], as_index=False)[["volume_usd", "fee_usd", "tx_count"]]
        .sum()
    )
    total = grouped.groupby("period")["volume_usd"].transform("sum")
    grouped["share"] = (grouped["volume_usd"] / total).where(total > 0)
    return grouped.sort_values(["period", "volume_usd"], ascending=[True, False]).reset_index(
        drop=True
    )


def concentration(shares: pd.DataFrame, key: str) -> pd.DataFrame:
    """Per period: number of entries, HHI, top-5 share, largest share and total volume."""
    rows = []
    for period, grp in shares.groupby("period"):
        s = grp["share"].dropna()
        if s.empty:
            continue
        rows.append(
            {
                "period": period,
                f"n_{key}": int((grp["volume_usd"] > 0).sum()),
                f"hhi_{key}": hhi(s),
                f"top{TOP_N}_{key}_share": top_share(s),
                f"max_{key}_share": float(s.max()),
            }
        )
    return pd.DataFrame(rows)


def symbols(daily: pd.DataFrame, tokens: pd.DataFrame) -> pd.DataFrame:
    """Explorer daily table with the origin asset's symbol; assets not in the list are unmapped."""
    mapping = tokens.drop_duplicates("asset_id").set_index("asset_id")["symbol"]
    out = daily.copy()
    out["symbol"] = out["asset_in"].map(mapping).fillna(UNMAPPED)
    return out


def asset_categories(by_symbol: pd.DataFrame) -> pd.DataFrame:
    """Share of the period's volume in ZEC, in stablecoins and in assets missing from the list."""
    rows = []
    for period, grp in by_symbol.groupby("period"):
        total = grp["volume_usd"].sum()
        if total <= 0:
            continue
        rows.append(
            {
                "period": period,
                "zec_share": float(
                    grp.loc[grp["symbol"] == ZEC_SYMBOL, "volume_usd"].sum() / total
                ),
                "stablecoin_share": float(
                    grp.loc[grp["symbol"].isin(STABLECOIN_SYMBOLS), "volume_usd"].sum() / total
                ),
                "unmapped_share": float(
                    grp.loc[grp["symbol"] == UNMAPPED, "volume_usd"].sum() / total
                ),
            }
        )
    return pd.DataFrame(rows)


def near_wallet_shares(daily: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Proxy for NEAR-run flow (not near.com): volume whose fee recipients are only NEAR revenue
    wallets, and volume with no app fee at all. `affiliate` joins a transaction's recipients."""

    def only_near(affiliate: str) -> bool:
        recipients = [r for r in affiliate.split(",") if r]
        return bool(recipients) and all(r in NEAR_WALLETS for r in recipients)

    frame = daily.assign(
        period=period_of(daily["date"], freq),
        near_only=daily["affiliate"].map(only_near),
        no_fee=daily["affiliate"] == "",
    )
    rows = []
    for period, grp in frame.groupby("period"):
        total = grp["volume_usd"].sum()
        if total <= 0:
            continue
        rows.append(
            {
                "period": period,
                "near_wallet_only_share": float(
                    grp.loc[grp["near_only"], "volume_usd"].sum() / total
                ),
                "no_app_fee_share": float(grp.loc[grp["no_fee"], "volume_usd"].sum() / total),
            }
        )
    return pd.DataFrame(rows)


def near_attribution(
    recipients: pd.DataFrame, onchain_revenue_usd: pd.Series, freq: str
) -> pd.DataFrame:
    """Declared app fee reaching NEAR revenue wallets, against what entered those wallets on chain.

    declared_fee_share_to_near: declared fee whose recipient is a NEAR wallet / all declared fee.
    attributable_share: that declared fee / on-chain revenue of the same days. The remainder is
    revenue that no Explorer transaction explains (other flows are not in this data).
    """
    frame = recipients.assign(period=period_of(recipients["date"], freq))
    frame["near"] = frame["recipient"].isin(NEAR_WALLETS)
    days = pd.Index(pd.to_datetime(recipients["date"]).unique())
    onchain = onchain_revenue_usd.reindex(days).dropna()
    onchain_by_period = onchain.groupby(
        period_of(pd.Series(onchain.index, index=onchain.index), freq)
    ).sum()
    rows = []
    for period, grp in frame.groupby("period"):
        total_fee = grp["fee_usd"].sum()
        near_fee = grp.loc[grp["near"], "fee_usd"].sum()
        on_chain = float(onchain_by_period.get(period, float("nan")))
        rows.append(
            {
                "period": period,
                "declared_fee_usd": float(total_fee),
                "declared_fee_near_usd": float(near_fee),
                "declared_fee_share_to_near": float(near_fee / total_fee)
                if total_fee > 0
                else None,
                "onchain_revenue_usd": None if pd.isna(on_chain) else on_chain,
                "attributable_share": float(near_fee / on_chain)
                if on_chain and on_chain > 0
                else None,
            }
        )
    return pd.DataFrame(rows)


def explorer_coverage(daily: pd.DataFrame, defillama: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Explorer (1Click) volume as a share of DefiLlama's volume, on the days both have."""
    ex = daily.groupby("date")["volume_usd"].sum().rename("explorer_usd")
    ex.index = pd.to_datetime(ex.index)
    dl = defillama.assign(date=pd.to_datetime(defillama["date"])).set_index("date")["volume_usd"]
    both = pd.concat([ex, dl.rename("defillama_usd")], axis=1, sort=True).dropna()
    both["period"] = period_of(pd.Series(both.index, index=both.index), freq)
    grouped = both.groupby("period")[["explorer_usd", "defillama_usd"]].sum()
    grouped["explorer_share_of_defillama_volume"] = (
        grouped["explorer_usd"] / grouped["defillama_usd"]
    )
    return grouped.reset_index()[["period", "explorer_share_of_defillama_volume"]]


def take_rates(defillama: pd.DataFrame) -> pd.DataFrame:
    """Implied average take rate per month from DefiLlama: fees / volume and revenue / volume.

    Long history (not limited to the Explorer window). Only days with volume, fees and revenue
    all present are used, so a month's rates never mix different sets of days.
    """
    frame = defillama.assign(date=pd.to_datetime(defillama["date"])).set_index("date")
    frame = frame[["volume_usd", "fees_usd", "revenue_usd"]].dropna()
    frame = frame[frame["volume_usd"] > 0]
    frame["period"] = period_of(pd.Series(frame.index, index=frame.index), "month")
    grouped = frame.groupby("period")[["volume_usd", "fees_usd", "revenue_usd"]].sum()
    grouped["fees_take_rate"] = grouped["fees_usd"] / grouped["volume_usd"]
    grouped["revenue_take_rate"] = grouped["revenue_usd"] / grouped["volume_usd"]
    grouped["days"] = frame.groupby("period").size()
    grouped["complete"] = [
        days == pd.Period(period, "M").days_in_month for period, days in grouped["days"].items()
    ]
    return grouped.reset_index()


def top_with_other(shares: pd.DataFrame, key: str, n: int) -> pd.DataFrame:
    """Keep the n largest entries per period; fold the rest into '(other)' so shares add to 1."""
    rows = []
    for period, grp in shares.groupby("period"):
        ordered = grp.sort_values("volume_usd", ascending=False)
        head, tail = ordered.head(n), ordered.iloc[n:]
        rows.extend(head.to_dict("records"))
        if not tail.empty:
            rows.append(
                {
                    "period": period,
                    key: "(other)",
                    "volume_usd": float(tail["volume_usd"].sum()),
                    "fee_usd": float(tail["fee_usd"].sum()) if "fee_usd" in tail else 0.0,
                    "tx_count": int(tail["tx_count"].sum()) if "tx_count" in tail else 0,
                    "share": float(tail["share"].sum()),
                }
            )
    return pd.DataFrame(rows)
