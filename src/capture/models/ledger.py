"""The capture ledger: where Intents volume goes, what closes the gap to break-even, and the
conditions that would change the thesis (docs/METHODOLOGY.md, "Ledger").

Pure functions over daily series indexed by UTC dates. NEAR amounts are valued at each day's price.
"""

from __future__ import annotations

import pandas as pd

from capture.models.valuation import breakeven_volume

LEDGER_COLUMNS = (
    "volume_usd",
    "fees_usd",
    "revenue_usd",
    "onchain_revenue_near",
    "buyback_near",
    "burnt_near",
    "issuance_gross_near",
    "near_usd",
)


def waterfall(daily: pd.DataFrame, end: pd.Timestamp, days: int = 30) -> dict:
    """Sums in USD of each step from Intents volume to the buyback wallet, over `days` to `end`.

    Every day of the window must have every input; a gap raises instead of shortening the window.
    """
    start = end - pd.Timedelta(days=days - 1)
    window = daily.loc[start:end, list(LEDGER_COLUMNS)]
    if len(window) != days or window.isna().any().any():
        missing = sorted(window.columns[window.isna().any()].tolist())
        raise ValueError(f"window {start.date()}..{end.date()} has missing inputs: {missing}")
    price = window["near_usd"]
    usd = {
        "volume": float(window["volume_usd"].sum()),
        "fees": float(window["fees_usd"].sum()),
        "revenue": float(window["revenue_usd"].sum()),
        "onchain_revenue": float((window["onchain_revenue_near"] * price).sum()),
        "buyback_wallet": float((window["buyback_near"] * price).sum()),
        "burn": float((window["burnt_near"] * price).sum()),
        "issuance": float((window["issuance_gross_near"] * price).sum()),
    }
    return {
        "start": start.date().isoformat(),
        "end": end.date().isoformat(),
        "days": days,
        "usd": usd,
        "per_10k_volume": {k: v / usd["volume"] * 10_000 for k, v in usd.items()},
        "kept": {
            "fees_of_volume": usd["fees"] / usd["volume"],
            "revenue_of_fees": usd["revenue"] / usd["fees"],
            "onchain_of_revenue": usd["onchain_revenue"] / usd["revenue"],
            "buyback_of_onchain": usd["buyback_wallet"] / usd["onchain_revenue"],
        },
    }


def lever_bridge(
    v0: float,
    supply: float,
    price: float,
    burnt_near_per_day: float,
    *,
    tau_buyback: float,
    tau_revenue: float,
    inflation_now: float,
    inflation_target: float,
) -> list[dict]:
    """The volume multiple needed for CR = 1, and how much each lever closes, applied in order.

    today: buyback take rate, current inflation. Then inflation falls to the target. Then every
    unit of protocol revenue goes to the buyback wallet. What is left must come from volume.
    The order is fixed; with burn small against issuance, the factors barely depend on it.
    """
    stages = [
        ("today", inflation_now, tau_buyback),
        ("inflation_to_target", inflation_target, tau_buyback),
        ("all_revenue_to_buybacks", inflation_target, tau_revenue),
    ]
    steps, previous = [], None
    for name, inflation, tau in stages:
        v_star = breakeven_volume(inflation, supply, price, burnt_near_per_day, tau)
        multiple = v_star / v0
        steps.append(
            {
                "step": name,
                "inflation": inflation,
                "tau_eff": tau,
                "v_star_usd_per_day": v_star,
                "volume_multiple": multiple,
                "closes_by": None if previous is None else previous / multiple,
            }
        )
        previous = multiple
    return steps


VOLUME_SCALES = (0.5, 1.0, 2.0)


def volume_scale_invariance(
    v0: float,
    supply: float,
    price: float,
    burnt_near_per_day: float,
    *,
    tau: float,
    inflation: float,
    scales: tuple[float, ...] = VOLUME_SCALES,
) -> dict:
    """V* and the multiple when the same revenue is divided by a volume counted differently.

    Public sources disagree on Intents volume (one- or two-sided counting, confidential flow). The
    revenue reaching the buyback wallet is measured on chain and does not depend on that choice:
    scaling volume by s divides tau by s, so V* scales by s and V*/V0 does not move. The multiple
    is therefore the revenue growth needed, whatever the volume definition.
    """
    revenue = tau * v0
    rows = []
    for scale in scales:
        volume = v0 * scale
        tau_s = revenue / volume
        v_star = breakeven_volume(inflation, supply, price, burnt_near_per_day, tau_s)
        rows.append(
            {
                "volume_scale": scale,
                "volume_usd_per_day": volume,
                "tau_eff": tau_s,
                "v_star_usd_per_day": v_star,
                "volume_multiple": v_star / volume,
            }
        )
    return {"buyback_usd_per_day": revenue, "inflation": inflation, "rows": rows}


# (id, label, numerator columns, window in days or "ytd", unit). Every row divides by gross
# issuance over the same days; "usd" values each day at that day's price.
DEFINITIONS = (
    ("headline", "Buyback wallet + gas burn, 30 days (the headline's basis)",
     ("buyback_near", "burnt_near"), 30, "usd"),
    ("window_90", "Buyback wallet + gas burn, 90 days",
     ("buyback_near", "burnt_near"), 90, "usd"),
    ("all_wallets", "All three revenue wallets + gas burn, 30 days",
     ("onchain_revenue_near", "burnt_near"), 30, "usd"),
    ("defillama_proxy", "DefiLlama holders revenue (as NEAR) + gas burn, 30 days",
     ("buyback_near_proxy", "burnt_near"), 30, "usd"),
    ("all_wallets_ytd", "All three revenue wallets, no burn, since 1 January, in NEAR",
     ("onchain_revenue_near",), "ytd", "near"),
    ("burn_only", "Gas burn only (total-supply view), 30 days, in NEAR",
     ("burnt_near",), 30, "near"),
)  # fmt: skip


def definition_table(daily: pd.DataFrame, end: pd.Timestamp) -> list[dict]:
    """Coverage of issuance under the definitions other public estimates use, on our own data.

    Same end day for every row. A day with an empty numerator counts as zero and is reported in
    `empty_days` (a source gap whose change lands on the next day keeps the sum whole).
    """
    rows = []
    for key, label, numerator, window, unit in DEFINITIONS:
        start = (
            pd.Timestamp(year=end.year, month=1, day=1)
            if window == "ytd"
            else end - pd.Timedelta(days=int(window) - 1)
        )
        frame = daily.loc[start:end]
        if frame["issuance_gross_near"].isna().any():
            raise ValueError(f"{key}: issuance missing in {start.date()}..{end.date()}")
        top = frame[list(numerator)].fillna(0.0).sum(axis=1)
        bottom = frame["issuance_gross_near"]
        if unit == "usd":
            top, bottom = top * frame["near_usd"], bottom * frame["near_usd"]
        rows.append(
            {
                "id": key,
                "label": label,
                "numerator": list(numerator),
                "start": start.date().isoformat(),
                "end": end.date().isoformat(),
                "days": len(frame),
                "unit": unit,
                "value": float(top.sum() / bottom.sum()),
                "empty_days": int(frame[list(numerator)].isna().any(axis=1).sum()),
            }
        )
    return rows


def conditions(
    volume: float,
    v_star: float,
    routed_share: float,
    worst_deviation: float,
    tolerance: float,
) -> list[dict]:
    """Three numeric conditions that would change the thesis, each evaluated on current data.

    Two would support it (effect "support") and move independently of each other: volume, and
    the share of protocol revenue that reaches the buyback wallet. (A take-rate condition would
    repeat the volume one: V0 / V* equals tau / tau-needed.) The third withdraws the headline.
    """
    return [
        {
            "id": "volume",
            "effect": "support",
            "text": "30-day average Intents volume reaches the break-even volume V*",
            "value": volume,
            "threshold": v_star,
            "unit": "USD/day",
            "met": volume >= v_star,
            "progress": volume / v_star,
        },
        {
            "id": "routing",
            "effect": "support",
            "text": "all protocol revenue that reaches NEAR wallets goes to the buyback wallet",
            "value": routed_share,
            "threshold": 1.0,
            "unit": "share of on-chain revenue",
            "met": routed_share >= 1.0,
            "progress": routed_share,
        },
        {
            "id": "reconciliation",
            "effect": "withdraw",
            "text": (
                "on-chain and DefiLlama revenue differ by more than the tolerance in a complete "
                "month: the headline is withdrawn until explained"
            ),
            "value": worst_deviation,
            "threshold": tolerance,
            "unit": "absolute monthly deviation",
            "met": worst_deviation > tolerance,
            "progress": worst_deviation / tolerance,
        },
    ]


def this_week(cr: pd.Series) -> dict:
    """Latest value of a daily series against the value 7 days earlier."""
    s = cr.dropna()
    last = s.index[-1]
    prev_date = last - pd.Timedelta(days=7)
    value, prev = float(s[last]), float(s[prev_date])
    return {
        "date": last.date().isoformat(),
        "value": value,
        "prev_date": prev_date.date().isoformat(),
        "prev": prev,
        "sentence": f"This week: CR 30d = {value:.3f} (prev {prev:.3f})",
    }


def largest_step_down(s: pd.Series, window: int = 14) -> pd.Timestamp:
    """First day of the largest fall between the mean of `window` days before and after it."""
    before = s.rolling(window, min_periods=window).mean().shift(1)
    after = s[::-1].rolling(window, min_periods=window).mean()[::-1]
    return (before / after).idxmax()


def step_down(s: pd.Series, window: int = 14) -> dict:
    """The largest fall in a daily series, dated to the first day closer to the new level.

    A change in the middle of a day leaves a transition day between the two levels; it is
    reported separately (transition_date) and kept out of both level means.
    """
    pivot = s.index.get_loc(largest_step_down(s, window))
    around = s.iloc[max(pivot - window, 0) : pivot + window]
    midpoint = (s.iloc[pivot - window : pivot].mean() + s.iloc[pivot : pivot + window].mean()) / 2
    pos = s.index.get_loc(around[around < midpoint].index[0])
    previous = s.iloc[pos - 1]
    transition = previous < s.iloc[pos - 1 - window : pos - 1].min()
    old_end = pos - 1 if transition else pos
    return {
        "date": s.index[pos],
        "transition_date": s.index[pos - 1] if transition else None,
        "before": float(s.iloc[old_end - window : old_end].mean()),
        "after": float(s.iloc[pos : pos + window].mean()),
    }
