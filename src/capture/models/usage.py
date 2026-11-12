"""Network usage: does NEAR's own activity move with Intents, and does Intents volume lead it?

Pure functions over network_daily, intents_onchain_daily, the DefiLlama table and price_daily (see
docs/METHODOLOGY.md, "Network usage").

"Daily active accounts" are distinct transaction signers per day; a relayed call is signed by its
relayer, so they are accounts, not people. Intents signers are signers of calls to `intents.near`,
mostly solvers and relayers. The lead/lag test describes co-movement of short weekly series: it
says nothing about cause, and a null result says only that nothing can be told apart from chance.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from capture.models import developer

WEEK = "W-SUN"  # weeks run Monday to Sunday
USAGE_METRICS = ("active_signers", "tx_count")
USAGE_LABELS = {"active_signers": "Daily active accounts", "tx_count": "Transactions"}
PREDICTORS = ("volume_usd", "near_usd")
PREDICTOR_LABELS = {"volume_usd": "Intents volume", "near_usd": "NEAR price"}
LAGS = (0, 1, 2, 3)
LEAD_LAGS = (1, 2, 3)  # lag 0 is co-movement, not a lead
HALF_COLUMNS = ("active_signers", "tx_count", "calls_to_intents", "volume_usd", "near_usd")
DAILY_COLUMNS = (
    "active_signers",
    "tx_count",
    "new_accounts",
    "function_calls",
    "calls_to_intents",
    "intents_signers",
    "volume_usd",
    "near_usd",
)
MEAN_COLUMNS = ("active_signers", "intents_signers", "near_usd")  # levels: weekly mean
# the other columns are counts or flows: weekly sum
RESULT_LABELS = {
    "supported": "supported",
    "not_supported": "not supported",
    "insufficient_data": "insufficient data",
}
CLOSING = {
    "supported": (
        "Volume passes out of sample for every usage series and more strongly than price; this "
        "describes co-movement, not a cause."
    ),
    "not_supported": (
        "Volume does not lead usage out of sample more reliably than price; with this few weeks "
        "that is a null result, not proof of absence."
    ),
    "insufficient_data": "Too few weekly pairs to choose a lag.",
}


def daily_table(
    network: pd.DataFrame,
    intents_onchain: pd.DataFrame,
    defillama: pd.DataFrame,
    price: pd.DataFrame,
) -> pd.DataFrame:
    """One row per day on which all four tables have a value, indexed by date."""
    frames = [
        network,
        intents_onchain.rename(columns={"unique_signers": "intents_signers"}),
        defillama[["date", "volume_usd"]],
        price[["date", "near_usd"]],
    ]
    dated = [f.assign(date=pd.to_datetime(f["date"])).set_index("date") for f in frames]
    joined = dated[0].join(dated[1:], how="inner")
    return joined[list(DAILY_COLUMNS)].dropna().sort_index()


def weekly_table(daily: pd.DataFrame) -> pd.DataFrame:
    """Complete Monday-to-Sunday weeks only: mean of levels, sum of counts and flows."""
    grouped = daily.groupby(daily.index.to_period(WEEK))
    how = {c: ("mean" if c in MEAN_COLUMNS else "sum") for c in daily.columns}
    weekly = grouped.agg(how)
    return weekly[grouped.size() == 7]


def shares(daily: pd.DataFrame) -> dict[str, float]:
    """How much of NEAR's activity is Intents: calls, and signers (mean of the daily ratio)."""
    return {
        "intents_call_share": float(
            daily["calls_to_intents"].sum() / daily["function_calls"].sum()
        ),
        "intents_signer_share": float((daily["intents_signers"] / daily["active_signers"]).mean()),
    }


def _half(frame: pd.DataFrame) -> dict:
    return {
        "start": frame.index[0].start_time.date().isoformat(),
        "end": frame.index[-1].end_time.date().isoformat(),
        "weeks": len(frame),
        **{c: float(frame[c].mean()) for c in HALF_COLUMNS},
    }


def halves(weekly: pd.DataFrame) -> dict:
    """Mean weekly value in the first n // 2 complete weeks against the rest, and the change."""
    n = len(weekly)
    first, second = _half(weekly.iloc[: n // 2]), _half(weekly.iloc[n // 2 :])
    return {
        "weeks": n,
        "first": first,
        "second": second,
        "change": {c: second[c] / first[c] - 1 for c in HALF_COLUMNS},
    }


def lead_lag_table(weekly: pd.DataFrame, split: str, seed: int = 0) -> pd.DataFrame:
    """Weekly log changes of each predictor against each usage series, lags 0 to 3 weeks.

    Train pairs lie wholly before the week `split`, test pairs start on or after it (as in
    developer.lead_lag). Raises ValueError if a weekly value cannot be logged.
    """
    for column in (*USAGE_METRICS, *PREDICTORS):
        if (weekly[column] <= 0).any():
            raise ValueError(f"{column}: every weekly value must be positive to take its log")
    parts = []
    for metric in USAGE_METRICS:
        for predictor in PREDICTORS:
            table = developer.lead_lag(
                np.log(weekly[predictor]),
                np.log(weekly[metric]),
                split,
                lags=LAGS,
                seed=seed,
                freq=WEEK,
            )
            table = table[table["transform"] == "diff"].drop(columns="transform")
            parts.append(table.assign(usage=metric, predictor=predictor))
    columns = ["usage", "predictor", "sample", "lag", "n", "pearson", "spearman", "p_value", "note"]
    return pd.concat(parts, ignore_index=True)[columns]


def _pick(table: pd.DataFrame, metric: str, predictor: str) -> dict | None:
    """The lead lag with the largest |r| in training, and that lag in the test weeks."""
    rows = table[(table["usage"] == metric) & (table["predictor"] == predictor)]
    train = rows[(rows["sample"] == "train") & rows["lag"].isin(LEAD_LAGS)]
    train = train[train["pearson"].notna()]
    if train.empty:
        return None
    order = train.assign(size=-train["pearson"].abs()).sort_values(["size", "lag"])
    chosen = order.iloc[0]
    test = rows[(rows["sample"] == "test") & (rows["lag"] == chosen["lag"])].iloc[0]
    if pd.isna(test["pearson"]):
        return None
    train_r, test_r = float(chosen["pearson"]), float(test["pearson"])
    p = None if pd.isna(test["p_value"]) else float(test["p_value"])
    return {
        "lag": int(chosen["lag"]),
        "train_r": train_r,
        "test_r": test_r,
        "test_n": int(test["n"]),
        "p_value": p,
        "leads": bool(
            p is not None and p < developer.ALPHA and np.sign(train_r) == np.sign(test_r)
        ),
    }


def _weeks(k: int) -> str:
    return f"{k} week" if k == 1 else f"{k} weeks"


def _side(predictor: str, s: dict) -> str:
    return (
        f"{PREDICTOR_LABELS[predictor]}, lag of {_weeks(s['lag'])}, r={s['train_r']:.2f} in "
        f"training and r={s['test_r']:.2f} on {s['test_n']} test weeks (p={s['p_value']:.2f})"
    )


def verdict(table: pd.DataFrame) -> dict:
    """Does Intents volume lead each usage series out of sample, and more strongly than price?"""
    by_usage, sentences = [], []
    for metric in USAGE_METRICS:
        volume, price = _pick(table, metric, "volume_usd"), _pick(table, metric, "near_usd")
        label = USAGE_LABELS[metric]
        if volume is None or price is None:
            result = "insufficient_data"
            sentences.append(f"{label}: too few weekly pairs.")
        else:
            if volume["leads"] and (
                not price["leads"] or abs(volume["test_r"]) > abs(price["test_r"])
            ):
                result = "volume_leads"
            elif price["leads"]:
                result = "price_leads"
            else:
                result = "null"
            sentences.append(f"{label}: {_side('volume_usd', volume)}; {_side('near_usd', price)}.")
        by_usage.append(
            {"usage": metric, "label": label, "result": result, "volume": volume, "price": price}
        )
    results = {u["result"] for u in by_usage}
    if "insufficient_data" in results:
        overall = "insufficient_data"
    elif results == {"volume_leads"}:
        overall = "supported"
    else:
        overall = "not_supported"
    return {
        "result": overall,
        "label": RESULT_LABELS[overall],
        "alpha": developer.ALPHA,
        "by_usage": by_usage,
        "text": " ".join([*sentences, CLOSING[overall]]),
    }
