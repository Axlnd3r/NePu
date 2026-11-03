"""Golden tests for the developer indicator on hand-made contracts.

Window starts 2026-01-01 (an anchor row), burn-in 30 days, data ends 2026-05-31.
    c1  deploys 2026-02-05 (no call that day), 5 calls in Mar, 2 in Apr, none in May
    c2  deploys 2026-02-10, 20 calls in Mar, none in Apr, 3 in May
    c3  called on 2026-01-15, deploys 2026-02-12     -> existed before: not new
    c4  deploys 2026-01-10                           -> inside the burn-in: not new
    c5  deploys 2026-03-03, 1 call in Apr, none in May
    c6  deploys 2026-01-31 (first eligible day), 4 calls in Feb: a Jan cohort cut by the burn-in
By hand:
    deploying accounts 6, dropped by burn-in 1 (c4), dropped as existing 1 (c3)
    Jan cohort {c6} is incomplete (the burn-in cuts its month), so it is left out of x
    Feb cohort {c1, c2}: +1 (Mar) 2/2, +2 (Apr) 1/2 (c1), +3 (May) 1/2 (c2)
    Mar cohort {c5}:     +1 (Apr) 1/1, +2 (May) 0/1, +3 (Jun) empty: after the data
    at least 10 calls:   Feb cohort +1 = 1/2 (only c2 has 20 calls; c1 has 5)
    retained new contracts x: Mar = 2 (Feb cohort, +1), Apr = 1 (Mar cohort, +1)
"""

import numpy as np
import pandas as pd
import pytest

from capture.models import developer as dev

D = pd.Timestamp


def _row(date: str, account: str, deploys: int = 0, calls: int = 0) -> dict:
    return {
        "date": D(date),
        "contract_account": account,
        "deploys": deploys,
        "function_calls_received": calls,
        "unique_callers": min(calls, 3),
    }


@pytest.fixture
def contracts() -> pd.DataFrame:
    rows = [
        _row("2026-01-01", "anchor.near", calls=1),
        _row("2026-02-05", "c1.near", deploys=1), _row("2026-03-10", "c1.near", calls=5),
        _row("2026-04-10", "c1.near", calls=2),
        _row("2026-02-10", "c2.near", deploys=1, calls=1), _row("2026-03-02", "c2.near", calls=19),
        _row("2026-05-04", "c2.near", calls=3),
        _row("2026-01-15", "c3.near", calls=2), _row("2026-02-12", "c3.near", deploys=1),
        _row("2026-01-10", "c4.near", deploys=1),
        _row("2026-03-03", "c5.near", deploys=1), _row("2026-04-01", "c5.near", calls=1),
        _row("2026-01-31", "c6.near", deploys=1), _row("2026-02-20", "c6.near", calls=4),
        _row("2026-05-31", "anchor.near", calls=1),
    ]  # fmt: skip
    return pd.DataFrame(rows)


def test_new_contract_rules(contracts: pd.DataFrame) -> None:
    new = dev.new_contracts(contracts)
    assert sorted(new["contract_account"]) == ["c1.near", "c2.near", "c5.near", "c6.near"]
    assert new.attrs == {"deploying_accounts": 6, "dropped_burn_in": 1, "dropped_existing": 1}


def test_retention_by_cohort(contracts: pd.DataFrame) -> None:
    new = dev.new_contracts(contracts)
    last = D("2026-05-31")
    table = dev.cohort_table(contracts, new, last).set_index("cohort")
    feb, mar = table.loc["2026-02"], table.loc["2026-03"]
    assert feb["cohort_size"] == 2
    assert table["complete"].to_dict() == {"2026-01": False, "2026-02": True, "2026-03": True}
    assert (feb["share_1"], feb["share_2"], feb["share_3"]) == (1.0, 0.5, 0.5)
    assert (mar["retained_1"], mar["retained_2"]) == (1, 0)
    assert mar["share_3"] is None or pd.isna(mar["share_3"])  # June is beyond the data

    strict = dev.cohort_table(contracts, new, last, min_calls=10).set_index("cohort")
    assert strict.loc["2026-02", "share_1"] == 0.5


def test_an_incomplete_month_is_never_used(contracts: pd.DataFrame) -> None:
    new = dev.new_contracts(contracts)
    mid_may = dev.cohort_table(contracts, new, D("2026-05-15")).set_index("cohort")
    assert pd.isna(mid_may.loc["2026-02", "share_3"])  # May is only half observed
    assert mid_may.loc["2026-02", "share_2"] == 0.5  # April is complete
    assert dev._last_complete_month(D("2026-05-31")) == pd.Period("2026-05")
    assert dev._last_complete_month(D("2026-05-30")) == pd.Period("2026-04")


def test_retained_new_contracts_series(contracts: pd.DataFrame) -> None:
    cohorts = dev.cohort_table(contracts, dev.new_contracts(contracts), D("2026-05-31"))
    x = dev.retained_new_contracts(cohorts)
    # the incomplete Jan cohort would have added Feb = 1 (c6 is called in Feb); it is left out
    assert x.to_dict() == {pd.Period("2026-03"): 2.0, pd.Period("2026-04"): 1.0}


def test_parent_account_labels() -> None:
    assert dev.parent_of("a.factory.near") == "factory.near"
    assert dev.parent_of("alice.near") == "near"
    assert dev.parent_of("near") == "(top-level)"
    assert dev.parent_of("a" * 64) == "(implicit account)"


def test_exact_permutation_p_value() -> None:
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    # perfect correlation: only the identity and the reversal reach |r| = 1, out of 5! = 120
    assert dev.permutation_p(x, x * 2, seed=0) == pytest.approx(2 / 120)


def test_lead_lag_recovers_a_known_lag_and_stays_null_on_noise() -> None:
    months = pd.period_range("2019-01", periods=96, freq="M")
    rng = np.random.default_rng(1)
    x = pd.Series(rng.normal(size=96), index=months)
    y = pd.Series(
        x.shift(2).to_numpy() + rng.normal(scale=0.1, size=96), index=months
    )  # y_t = x_{t-2}
    table = dev.lead_lag(x, y, split="2023-01", seed=0)
    levels = table[table["transform"] == "levels"].set_index(["sample", "lag"])
    for sample in ("train", "test"):
        assert levels.loc[(sample, 2), "pearson"] > 0.95
        assert abs(levels.loc[(sample, 0), "pearson"]) < 0.5
    assert (
        dev.verdict(table)["lag_chosen_in_train"] == 2
        and dev.verdict(table)["result"] == "association"
    )

    noise = pd.Series(np.random.default_rng(2).normal(size=96), index=months)
    verdict = dev.verdict(dev.lead_lag(x, noise, split="2023-01", seed=0))
    assert verdict["result"] == "null"


def test_lead_lag_never_mixes_train_and_test_months() -> None:
    months = pd.period_range("2026-01", periods=10, freq="M")
    x, y = (
        pd.Series(range(10), index=months, dtype=float),
        pd.Series(range(10), index=months, dtype=float),
    )
    split = pd.Period("2026-06", "M")
    for lag in (0, 1, 2, 3):
        xs, _ = dev._pairs(x, y, lag, "levels", "train", split)
        assert (xs + lag < 5).all()  # both x_t and y_{t+lag} before June (index 5)
        xt, _ = dev._pairs(x, y, lag, "levels", "test", split)
        assert (xt >= 5).all()


def test_too_few_points_gives_no_correlation() -> None:
    months = pd.period_range("2026-01", periods=6, freq="M")
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], index=months)
    table = dev.lead_lag(s, s, split="2026-04", seed=0)
    short = table[
        (table["transform"] == "levels") & (table["sample"] == "test") & (table["lag"] == 3)
    ].iloc[0]
    assert short["n"] < dev.MIN_PAIRS and short["pearson"] is None and "fewer than" in short["note"]


def test_verdict_text_makes_no_causal_claim() -> None:
    months = pd.period_range("2019-01", periods=96, freq="M")
    rng = np.random.default_rng(1)
    x = pd.Series(rng.normal(size=96), index=months)
    for y in (x.shift(1).fillna(0), pd.Series(rng.normal(size=96), index=months)):
        text = dev.verdict(dev.lead_lag(x, y, split="2023-01", seed=0))["text"].lower()
        for forbidden in ("causes", "drives", "leads to", "because", "results in"):
            assert forbidden not in text
