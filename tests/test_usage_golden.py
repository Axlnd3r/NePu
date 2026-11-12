"""Golden tests for the network usage model on hand-made tables.

Days start on Monday 2026-06-01, so week k covers days 7k..7k+6. Daily values are held constant
inside a week, so a week's mean equals the daily value and a week's sum is seven times it; weekly
log changes are then the changes written in each test.
"""

import numpy as np
import pandas as pd
import pytest

from capture.models import usage

START = "2026-06-01"  # a Monday
SPLIT = "2026-07-27"  # week 9 of 16


def inputs(
    days: int,
    *,
    active=None,
    tx=None,
    function_calls=None,
    calls=None,
    signers=None,
    volume=None,
    price=None,
    drop_price: tuple[str, ...] = (),
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """The four input tables (network, intents_onchain, defillama, price) for `days` days."""
    dates = pd.date_range(START, periods=days, freq="D")

    def col(values, default):
        return list(values) if values is not None else [default] * days

    network = pd.DataFrame(
        {
            "date": dates.date,
            "active_signers": col(active, 100),
            "tx_count": col(tx, 10),
            "new_accounts": [1] * days,
            "function_calls": col(function_calls, 100),
        }
    )
    intents = pd.DataFrame(
        {"date": dates.date, "calls_to_intents": col(calls, 5), "unique_signers": col(signers, 2)}
    )
    llama = pd.DataFrame(
        {
            "date": dates.date,
            "volume_usd": col(volume, 1000.0),
            "fees_usd": [1.0] * days,
            "revenue_usd": [0.5] * days,
            "holders_revenue_usd": [0.5] * days,
        }
    )
    prices = pd.DataFrame({"date": dates.date, "near_usd": col(price, 2.0)})
    prices = prices[~prices["date"].astype(str).isin(drop_price)]
    return network, intents, llama, prices


def daily_from_weekly(values: np.ndarray) -> list[float]:
    """Each weekly level held for the seven days of its week."""
    return [float(v) for v in np.repeat(values, 7)]


def levels(changes: list[float], first: float = 100.0) -> np.ndarray:
    return first * np.exp(np.concatenate([[0.0], np.cumsum(changes)]))


# Volume's weekly log changes, and a pattern for the predictor that does not drive usage.
DRIVER = [0.3, -0.2, 0.5, -0.4, 0.1, 0.25, -0.35, 0.15, -0.05, 0.4, -0.3, 0.2, -0.15, 0.35, -0.25]
OTHER = [
    0.05, 0.12, -0.08, 0.02, -0.11, 0.07, 0.09, -0.04,
    -0.06, 0.1, 0.03, -0.09, 0.01, 0.08, -0.02,
]  # fmt: skip


def follower(driver: list[float]) -> np.ndarray:
    """Usage whose log change in week t is the driver's change in week t - 1."""
    return levels([0.1, *driver[:-1]])


def weekly_case(usage_levels: np.ndarray, volume_levels: np.ndarray, price_levels: np.ndarray):
    daily = usage.daily_table(
        *inputs(
            7 * len(usage_levels),
            active=daily_from_weekly(usage_levels),
            tx=daily_from_weekly(usage_levels),
            volume=daily_from_weekly(volume_levels),
            price=daily_from_weekly(price_levels),
        )
    )
    return usage.weekly_table(daily)


def test_only_complete_weeks_are_kept_and_aggregated() -> None:
    active = [100] * 7 + [200] * 7 + [400] * 9  # three full weeks and two days of a fourth
    daily = usage.daily_table(*inputs(23, active=active))
    weekly = usage.weekly_table(daily)
    assert [str(p.start_time.date()) for p in weekly.index] == [
        "2026-06-01",
        "2026-06-08",
        "2026-06-15",
    ]
    assert weekly["active_signers"].tolist() == [100.0, 200.0, 400.0]  # mean
    assert weekly["tx_count"].tolist() == [70, 70, 70]  # sum of 10 a day


def test_a_week_with_a_missing_day_in_any_input_is_dropped() -> None:
    daily = usage.daily_table(*inputs(21, drop_price=("2026-06-10",)))
    weekly = usage.weekly_table(daily)
    assert [str(p.start_time.date()) for p in weekly.index] == ["2026-06-01", "2026-06-15"]


def test_the_daily_table_renames_the_intents_signers() -> None:
    daily = usage.daily_table(*inputs(7))
    assert "intents_signers" in daily.columns and "unique_signers" not in daily.columns
    assert isinstance(daily.index, pd.DatetimeIndex)


def test_shares() -> None:
    active = [100] * 7 + [200] * 7 + [400] * 7
    s = usage.shares(usage.daily_table(*inputs(21, active=active)))
    assert s["intents_call_share"] == pytest.approx(0.05)
    assert s["intents_signer_share"] == pytest.approx((0.02 * 7 + 0.01 * 7 + 0.005 * 7) / 21)


def test_halves_compare_the_first_weeks_with_the_rest() -> None:
    active = [100] * 7 + [200] * 7 + [400] * 7
    h = usage.halves(usage.weekly_table(usage.daily_table(*inputs(21, active=active))))
    assert h["weeks"] == 3 and h["first"]["weeks"] == 1 and h["second"]["weeks"] == 2
    assert h["first"]["start"] == "2026-06-01" and h["second"]["end"] == "2026-06-21"
    assert h["change"]["active_signers"] == pytest.approx(300 / 100 - 1)


def test_volume_leads_when_usage_repeats_last_weeks_volume_change() -> None:
    weekly = weekly_case(follower(DRIVER), levels(DRIVER), levels(OTHER, 2.0))
    v = usage.verdict(usage.lead_lag_table(weekly, SPLIT))
    by = {u["usage"]: u for u in v["by_usage"]}
    assert by["active_signers"]["result"] == "volume_leads"
    assert by["active_signers"]["volume"]["lag"] == 1
    assert by["active_signers"]["volume"]["leads"] is True


def test_price_leads_when_the_roles_are_swapped() -> None:
    weekly = weekly_case(follower(DRIVER), levels(OTHER, 1000.0), levels(DRIVER, 2.0))
    v = usage.verdict(usage.lead_lag_table(weekly, SPLIT))
    by = {u["usage"]: u for u in v["by_usage"]}
    assert by["active_signers"]["result"] == "price_leads"
    assert v["result"] == "not_supported" and v["label"] == "not supported"


def test_usage_without_change_gives_insufficient_data() -> None:
    weekly = weekly_case(np.full(16, 100.0), levels(DRIVER), levels(OTHER, 2.0))
    v = usage.verdict(usage.lead_lag_table(weekly, SPLIT))
    assert v["result"] == "insufficient_data" and v["label"] == "insufficient data"


def test_a_non_positive_weekly_value_is_refused() -> None:
    volume = levels(DRIVER)
    volume[4] = 0.0
    weekly = weekly_case(follower(DRIVER), volume, levels(OTHER, 2.0))
    with pytest.raises(ValueError, match="volume_usd"):
        usage.lead_lag_table(weekly, SPLIT)


def test_the_table_covers_every_metric_predictor_sample_and_lag() -> None:
    weekly = weekly_case(follower(DRIVER), levels(DRIVER), levels(OTHER, 2.0))
    table = usage.lead_lag_table(weekly, SPLIT)
    assert len(table) == 2 * 2 * 2 * 4
    assert list(table.columns) == [
        "usage", "predictor", "sample", "lag", "n", "pearson", "spearman", "p_value", "note",
    ]  # fmt: skip


def test_the_verdict_text_states_every_number_it_rests_on() -> None:
    weekly = weekly_case(follower(DRIVER), levels(DRIVER), levels(OTHER, 2.0))
    v = usage.verdict(usage.lead_lag_table(weekly, SPLIT))
    assert "Daily active accounts" in v["text"] and "Transactions" in v["text"]
    for u in v["by_usage"]:
        for side in ("volume", "price"):
            assert f"r={u[side]['train_r']:.2f}" in v["text"]
            assert f"r={u[side]['test_r']:.2f}" in v["text"]
