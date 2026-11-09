"""Gross flows of the buyback wallet, rebuilt from its balance-changing activities (a check).

The coverage ratio reads the buyback wallet as a net daily balance change. That cannot show an
outflow on a day with a larger inflow, nor who sent an inflow. NearBlocks lists every balance
change with the balance after it and the counterparty, so the change of each activity is the
difference of consecutive balances. Pure functions; amounts in NEAR.
"""

from __future__ import annotations

import pandas as pd

YOCTO = 10**24
SOURCE = "intents.near"


def activity_changes(activities: list[dict], revenue_wallets: set[str]) -> pd.DataFrame:
    """One row per activity: date, counterparty, its class and the change of the balance."""
    frame = pd.DataFrame(activities)
    order = sorted(range(len(frame)), key=lambda i: int(frame["event_index"].iloc[i]))
    frame = frame.iloc[order]  # event indexes exceed int64 too
    # yoctoNEAR balances exceed int64: difference them as Python integers, then convert.
    balance = [int(b) for b in frame["absolute_nonstaked_amount"]]
    change = pd.Series(
        [(b - a) / YOCTO for a, b in zip([0, *balance[:-1]], balance, strict=True)],
        index=frame.index,
    )
    stamp = pd.to_datetime(frame["block_timestamp"].astype("int64"), unit="ns", utc=True)
    counterparty = frame["involved_account_id"].fillna("(none)")
    kind = counterparty.map(
        lambda a: (
            "intents" if a == SOURCE else "revenue_wallet" if a in revenue_wallets else "other"
        )
    )
    return pd.DataFrame(
        {
            "timestamp": stamp.dt.tz_localize(None),
            "date": stamp.dt.tz_localize(None).dt.normalize(),
            "counterparty": counterparty,
            "kind": kind,
            "change_near": change,
        }
    ).reset_index(drop=True)


def gross_flows(changes: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    """Inflows by class, every outflow, and the net, over [start, end] (UTC days)."""
    window = changes[(changes["date"] >= start) & (changes["date"] <= end)]
    inflow = window[window["change_near"] > 0]
    outflow = window[window["change_near"] < 0]
    by_kind = inflow.groupby("kind")["change_near"].sum()
    others = (
        inflow[inflow["kind"] == "other"]
        .groupby("counterparty")["change_near"]
        .sum()
        .sort_values(ascending=False)
    )
    return {
        "start": start.date().isoformat(),
        "end": end.date().isoformat(),
        "inflow_near": {
            k: float(by_kind.get(k, 0.0)) for k in ("intents", "revenue_wallet", "other")
        },
        "other_senders": int(others.size),
        "other_largest": [{"account": a, "near": float(v)} for a, v in others.head(5).items()],
        "outflow_near": float(-outflow["change_near"].sum()),
        "outflows": [
            {"date": d.date().isoformat(), "to": c, "near": float(-v)}
            for d, c, v in outflow[["date", "counterparty", "change_near"]].itertuples(index=False)
        ],
        "net_near": float(window["change_near"].sum()),
    }
