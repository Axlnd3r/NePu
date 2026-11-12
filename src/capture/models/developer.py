"""Developer indicator: do newly deployed contracts stay in use, and does that move with revenue?

Pure functions over contracts_daily and the DefiLlama table (see docs/METHODOLOGY.md).

A "new contract" is an account whose first observed DEPLOY_CONTRACT falls after a burn-in period
from the start of the data and which had no row (no call, no deploy) before that day. A deploy can
also be an upgrade of an older contract; the burn-in and the "no earlier row" rule reduce but do
not remove that. The lead/lag test describes co-movement of two short monthly series. It says
nothing about cause.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd

BURN_IN_DAYS = 30
RETENTION_LAGS = (1, 2, 3)
MIN_CALLS_STRICT = 10
LAGS = (0, 1, 2, 3)
MIN_PAIRS = 4  # fewer pairs than this cannot give a correlation worth reporting
EXACT_PERMUTATION_MAX_N = 8  # n! permutations are enumerated up to here, a seeded sample above
MONTE_CARLO_DRAWS = 10_000
ALPHA = 0.1


def _month(dates: pd.Series) -> pd.Series:
    return pd.to_datetime(dates).dt.to_period("M")


def new_contracts(contracts: pd.DataFrame, burn_in_days: int = BURN_IN_DAYS) -> pd.DataFrame:
    """One row per new contract: first deploy date and month, plus how many were excluded.

    Returns columns contract_account, first_deploy (Timestamp), cohort (Period[M]). The number of
    deploying accounts dropped by the burn-in and by the earlier-row rule is in `.attrs`.
    """
    frame = contracts.assign(date=pd.to_datetime(contracts["date"]))
    window_start = frame["date"].min()
    first_row = frame.groupby("contract_account")["date"].min()
    first_deploy = frame.loc[frame["deploys"] > 0].groupby("contract_account")["date"].min()
    deploying = pd.DataFrame({"first_deploy": first_deploy, "first_row": first_row}).dropna()
    in_burn_in = deploying["first_deploy"] < window_start + pd.Timedelta(days=burn_in_days)
    existed = deploying["first_row"] < deploying["first_deploy"]
    keep = deploying[~in_burn_in & ~existed].reset_index(names="contract_account")
    keep["cohort"] = keep["first_deploy"].dt.to_period("M")
    keep.attrs = {
        "deploying_accounts": len(deploying),
        "dropped_burn_in": int(in_burn_in.sum()),
        "dropped_existing": int((~in_burn_in & existed).sum()),
    }
    return keep[["contract_account", "first_deploy", "cohort"]]


def parent_of(account: str) -> str:
    """Parent of a sub-account ('a.factory.near' -> 'factory.near'); other kinds get a label."""
    if len(account) == 64 and all(c in "0123456789abcdef" for c in account):
        return "(implicit account)"
    return account.split(".", 1)[1] if "." in account else "(top-level)"


def cohort_table(
    contracts: pd.DataFrame,
    new: pd.DataFrame,
    last_date: pd.Timestamp,
    min_calls: int = 1,
    lags: tuple[int, ...] = RETENTION_LAGS,
    burn_in_days: int = BURN_IN_DAYS,
) -> pd.DataFrame:
    """Per cohort month: size and, for each lag k, the share active in month +k.

    Active in a month = at least `min_calls` FUNCTION_CALLs received in it. A lag whose month is
    not complete in the data (or beyond it) is left empty rather than computed on part of a month.
    """
    frame = contracts.assign(month=_month(contracts["date"]))
    monthly_calls = frame.groupby(["contract_account", "month"])["function_calls_received"].sum()
    active: dict[pd.Period, set[str]] = {
        month: set(grp.index.get_level_values(0))
        for month, grp in monthly_calls[monthly_calls >= min_calls].groupby(level=1)
    }
    last_complete = _last_complete_month(last_date)
    first_eligible = pd.to_datetime(contracts["date"]).min() + pd.Timedelta(days=burn_in_days)
    rows = []
    for cohort, grp in new.groupby("cohort"):
        members = set(grp["contract_account"])
        parents = grp["contract_account"].map(parent_of).value_counts()
        row: dict = {
            "cohort": str(cohort),
            # A cohort is comparable with the others only if its whole month was observable.
            "complete": bool(
                cohort.start_time >= first_eligible and cohort.end_time.normalize() <= last_date
            ),
            "cohort_size": len(members),
            "top_parent": parents.index[0],
            "top_parent_share": float(parents.iloc[0] / len(members)),
        }
        for k in lags:
            target = cohort + k
            if target <= last_complete:
                retained = len(members & active.get(target, set()))
                row[f"retained_{k}"] = retained
                row[f"share_{k}"] = retained / len(members)
            else:
                row[f"retained_{k}"], row[f"share_{k}"] = None, None
        rows.append(row)
    return pd.DataFrame(rows)


def _last_complete_month(last_date: pd.Timestamp) -> pd.Period:
    """The last month that ends on or before the last day of data."""
    month = last_date.to_period("M")
    return month if last_date == month.end_time.normalize() else month - 1


def retained_new_contracts(cohorts: pd.DataFrame) -> pd.Series:
    """x(t) = contracts first deployed in month t-1 that are still receiving calls in month t.

    Only complete cohorts are used: a cohort cut short by the burn-in or by the end of the data
    is smaller for that reason alone and would not be comparable with the others.
    """
    valid = cohorts[cohorts["complete"]].dropna(subset=["retained_1"])
    index = [pd.Period(c, "M") + 1 for c in valid["cohort"]]
    return pd.Series(
        valid["retained_1"].astype(float).to_numpy(), index=pd.PeriodIndex(index, freq="M")
    )


def monthly_revenue(defillama: pd.DataFrame) -> pd.Series:
    """DefiLlama revenue in USD per calendar month, complete months only."""
    frame = defillama.assign(date=pd.to_datetime(defillama["date"])).set_index("date")[
        "revenue_usd"
    ]
    frame = frame.dropna()
    grouped = frame.groupby(frame.index.to_period("M"))
    sums, days = grouped.sum(), grouped.size()
    complete = [days[m] == m.days_in_month for m in sums.index]
    return sums[complete]


def _pearson(x: np.ndarray, y: np.ndarray) -> float | None:
    if len(x) < 2 or np.std(x) == 0 or np.std(y) == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def _spearman(x: np.ndarray, y: np.ndarray) -> float | None:
    return _pearson(pd.Series(x).rank().to_numpy(), pd.Series(y).rank().to_numpy())


def permutation_p(x: np.ndarray, y: np.ndarray, seed: int) -> float | None:
    """Two-sided p-value for |Pearson r| by permuting y: exact for small n, seeded sample above."""
    observed = _pearson(x, y)
    if observed is None:
        return None
    n = len(x)
    xs = (x - x.mean()) / x.std()
    ys = (y - y.mean()) / y.std()
    if n <= EXACT_PERMUTATION_MAX_N:
        order = np.array(list(itertools.permutations(range(n))))
        shuffled = ys[order]
    else:
        rng = np.random.default_rng(seed)
        shuffled = rng.permuted(np.tile(ys, (MONTE_CARLO_DRAWS, 1)), axis=1)
    r = (shuffled * xs).mean(axis=1)  # Pearson r with population standard deviations
    return float(np.mean(np.abs(r) >= abs(observed) - 1e-12))


def _pairs(
    x: pd.Series, y: pd.Series, lag: int, transform: str, sample: str, split: pd.Period
) -> tuple[np.ndarray, np.ndarray]:
    """Pairs (x_t, y_{t+lag}). Train: both months before `split`. Test: t on or after `split`."""
    if transform == "diff":
        x, y = x.diff(), y.diff()
    rows = []
    for t, xv in x.dropna().items():
        yv = y.get(t + lag)
        if yv is None or pd.isna(yv):
            continue
        in_train = t + lag < split
        in_test = t >= split
        if (sample == "train" and in_train) or (sample == "test" and in_test):
            rows.append((xv, yv))
    arr = np.array(rows, dtype=float).reshape(-1, 2)
    return arr[:, 0], arr[:, 1]


def lead_lag(
    x: pd.Series,
    y: pd.Series,
    split: str,
    lags: tuple[int, ...] = LAGS,
    seed: int = 0,
    freq: str = "M",
) -> pd.DataFrame:
    """Cross-correlation of x (leading) with y at each lag, train and test, levels and differences.

    Train pairs lie entirely before `split` and test pairs start on or after it, so nothing in the
    test sample was used to look at the train sample. Fewer than MIN_PAIRS pairs gives no value.
    x and y carry a PeriodIndex of frequency `freq` (months by default; "W-SUN" for weeks).
    """
    cut = pd.Period(split, freq)
    months = pd.period_range(
        min(x.index.min(), y.index.min()), max(x.index.max(), y.index.max()), freq=freq
    )
    x, y = x.reindex(months), y.reindex(months)  # a missing month stays empty, so diff() is exact
    rows = []
    for transform in ("levels", "diff"):
        for sample in ("train", "test"):
            for lag in lags:
                xs, ys = _pairs(
                    x, y, lag, "levels" if transform == "levels" else "diff", sample, cut
                )
                enough = len(xs) >= MIN_PAIRS
                rows.append(
                    {
                        "transform": transform,
                        "sample": sample,
                        "lag": lag,
                        "n": len(xs),
                        "pearson": _pearson(xs, ys) if enough else None,
                        "spearman": _spearman(xs, ys) if enough else None,
                        "p_value": permutation_p(xs, ys, seed + lag) if enough else None,
                        "note": None if enough else f"fewer than {MIN_PAIRS} pairs",
                    }
                )
    return pd.DataFrame(rows)


def verdict(table: pd.DataFrame) -> dict:
    """Pick the lag with the largest |r| in train (levels) and look at that lag in test.

    The wording never claims a cause: it states whether the out-of-sample correlation at the lag
    chosen on the training months is distinguishable from chance, given the few points available.
    """
    train = table[(table["transform"] == "levels") & (table["sample"] == "train")].dropna(
        subset=["pearson"]
    )
    if train.empty:
        return {
            "result": "insufficient_data",
            "text": "Too few monthly points in the training months to choose a lag.",
        }
    chosen = int(train.loc[train["pearson"].abs().idxmax(), "lag"])
    test = table[
        (table["transform"] == "levels") & (table["sample"] == "test") & (table["lag"] == chosen)
    ].iloc[0]
    if test["pearson"] is None or pd.isna(test["pearson"]):
        return {
            "result": "insufficient_data",
            "lag_chosen_in_train": chosen,
            "text": f"Lag {chosen} was chosen in training; the test months have too few pairs.",
        }
    train_r = float(train.loc[train["lag"] == chosen, "pearson"].iloc[0])
    same_sign = math.copysign(1, train_r) == math.copysign(1, test["pearson"])
    significant = test["p_value"] is not None and test["p_value"] < ALPHA
    result = "association" if significant and same_sign else "null"
    text = (
        f"Lag {chosen} had the largest correlation in training (r={train_r:.2f}). In the "
        f"test months it is r={test['pearson']:.2f} on {int(test['n'])} pairs "
        f"(permutation p={test['p_value']:.2f}). "
    )
    text += (
        "That is unlikely under chance alone, but it describes co-movement of two short series, "
        "not a cause."
        if result == "association"
        else "That cannot be told apart from chance with this few points; this is a null result."
    )
    return {"result": result, "lag_chosen_in_train": chosen, "alpha": ALPHA, "text": text}
