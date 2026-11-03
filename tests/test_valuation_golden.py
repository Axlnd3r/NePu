"""Golden tests for the Valuation Lab functions on tiny hand-made inputs.

Break-even and CR, worked by hand (supply S = 365 M NEAR, inflation i = 2 %, price P = 2 USD):
    issuance = i * S / 365 = 20,000 NEAR/day = 40,000 USD/day
    volume V0 = 100 M USD/day, tau = 0.03 %  ->  buyback = 30,000 USD/day
    burn = 1,000 NEAR/day = 2,000 USD/day
    CR = (30,000 + 2,000) / 40,000 = 0.8
    at price x2 (P = 4): buyback stays 30,000 USD, burn 4,000, issuance 80,000 -> CR = 0.425
"""

import numpy as np
import pandas as pd
import pytest

from capture.models import breakeven
from capture.models import valuation as val

SUPPLY, PRICE, BURN, V0, TAU = 365e6, 2.0, 1_000.0, 100e6, 0.0003


@pytest.fixture
def inputs() -> val.Inputs:
    return val.Inputs(
        volume_usd_per_day=V0,
        total_supply_near=SUPPLY,
        near_usd=PRICE,
        burnt_near_per_day=BURN,
        tau_min=TAU,
        tau_max=TAU,
    )


def test_breakeven_volume_agrees_with_the_f3_sensitivity_grid() -> None:
    grid = breakeven.sensitivity_grid(SUPPLY, PRICE, BURN, TAU).set_index(
        ["inflation", "price_multiplier", "tau_multiplier"]
    )
    for inflation in (0.025, 0.016):
        expected = grid.loc[(inflation, 1.0, 1.0), "v_star_usd_per_day"]
        got = val.breakeven_volume(inflation, SUPPLY, PRICE, BURN, TAU)
        assert got == pytest.approx(expected)


def test_breakeven_volume_is_zero_when_burn_covers_issuance() -> None:
    assert val.breakeven_volume(0.02, SUPPLY, PRICE, 50_000.0, TAU) == 0.0


def test_required_growth_is_a_compound_annual_rate() -> None:
    # 100 -> 800 in 3 years is 2x per year, i.e. +100 % a year; in 1 year it is +700 %.
    assert val.required_cagr(100.0, 800.0, 3) == pytest.approx(1.0)
    assert val.required_cagr(100.0, 800.0, 1) == pytest.approx(7.0)
    assert val.required_cagr(800.0, 100.0, 3) == pytest.approx(-0.5)  # may shrink and still reach


def test_reverse_table_has_every_horizon_inflation_and_basis(inputs: val.Inputs) -> None:
    table = val.reverse_table(inputs, taus={"buyback": TAU, "revenue": 2 * TAU})
    assert len(table) == 3 * 2 * 2
    row = table[
        (table.horizon_years == 3) & (table.inflation == 0.025) & (table.basis == "buyback")
    ]
    assert len(row) == 1
    v_star = val.breakeven_volume(0.025, SUPPLY, PRICE, BURN, TAU)
    assert row.iloc[0]["required_cagr"] == pytest.approx((v_star / V0) ** (1 / 3) - 1)
    assert row.iloc[0]["breakeven_volume_usd_per_day"] == pytest.approx(v_star)


def test_inflation_path_is_constant_or_ramps_linearly_then_holds() -> None:
    flat = val.inflation_path(60, start=0.025)
    assert flat.shape == (60,) and set(flat) == {0.025}
    ramp = val.inflation_path(60, start=0.025, end=0.016, ramp_months=24)
    assert ramp[11] == pytest.approx(0.025 - 0.009 * 12 / 24)  # month 12: halfway
    assert ramp[23] == pytest.approx(0.016)  # month 24: arrived
    assert ramp[24:] == pytest.approx(0.016)  # then held


def test_monthly_log_growth_uses_the_daily_average_of_each_month() -> None:
    days = pd.date_range("2025-06-01", "2025-08-31", freq="D")
    volume = pd.Series(
        np.where(days.month == 6, 10.0, np.where(days.month == 7, 20.0, 80.0)), index=days
    )
    growth = val.monthly_log_growth(volume, start="2025-06-01")
    assert growth.tolist() == pytest.approx([np.log(2.0), np.log(4.0)])
    assert [d.strftime("%Y-%m") for d in growth.index] == ["2025-07", "2025-08"]


def test_block_bootstrap_draws_consecutive_blocks() -> None:
    growth = np.arange(10, dtype=float)  # 0..9, so a block shows as +1 steps
    draws = val.block_bootstrap(
        growth, n_paths=200, n_months=6, block=3, rng=np.random.default_rng(1)
    )
    assert draws.shape == (200, 6)
    assert set(np.unique(draws)) <= set(growth)
    within = np.diff(draws.reshape(200, 2, 3), axis=2)
    assert (within == 1.0).all()


def test_block_bootstrap_needs_at_least_one_full_block() -> None:
    with pytest.raises(ValueError, match="block"):
        val.block_bootstrap(np.array([0.1, 0.2]), 10, 6, 3, np.random.default_rng(1))


def test_cr_with_no_growth_matches_the_hand_calculation(inputs: val.Inputs) -> None:
    zero = np.zeros((4, 60))
    tau = np.full(4, TAU)
    cr = val.cr_paths(zero, tau, val.inflation_path(60, 0.02), inputs)
    assert cr.shape == (4, 60)
    assert cr == pytest.approx(0.8)
    cr_2x = val.cr_paths(zero, tau, val.inflation_path(60, 0.02), inputs, price_multiplier=2.0)
    assert cr_2x == pytest.approx(0.425)


def test_summary_of_paths_that_cross_and_paths_that_do_not() -> None:
    cr = np.full((4, 60), 0.5)
    cr[:2, 10:] = 2.0  # two paths cross at month 11 (index 10) and stay above 1
    s = val.summarize(cr)
    assert s["p_cr_ge_1"] == {"12": 0.5, "36": 0.5, "60": 0.5}
    assert s["share_reaching_by_60"] == 0.5
    assert s["median_first_month"] == "not reached"  # only half of the paths ever cross
    cr[2:, 20:] = 3.0  # now every path crosses; the median is between month 11 and 21
    assert val.summarize(cr)["median_first_month"] == pytest.approx(16.0)
    assert val.summarize(np.full((4, 60), 0.5))["median_first_month"] == "not reached"
    assert set(s["fan"]) == {"p10", "p50", "p90"} and len(s["fan"]["p50"]) == 60


def test_scenarios_are_ordered_path_by_path_when_the_historical_drift_is_positive() -> None:
    boot = np.random.default_rng(3).normal(0.05, 0.1, size=(50, 60))
    mu = 0.05
    a = val.scenario_growth("historical", boot, mu)
    b = val.scenario_growth("decay", boot, mu)
    c = val.scenario_growth("flat", boot, mu)
    assert (c <= b + 1e-12).all() and (b <= a + 1e-12).all()
    assert c.mean() == pytest.approx(0.0, abs=0.03)  # zero drift in expectation
    # decay: the drift term halves every 12 months, month 13 carries half of month 1's
    drift = (b - c).mean(axis=0)
    assert drift[0] == pytest.approx(mu) and drift[12] == pytest.approx(mu / 2)


def test_unknown_scenario_is_rejected() -> None:
    with pytest.raises(ValueError, match="scenario"):
        val.scenario_growth("moon", np.zeros((2, 3)), 0.0)


def test_monthly_tau_uses_aligned_days_and_drops_thin_months() -> None:
    jan = pd.date_range("2026-01-01", "2026-01-31", freq="D")
    feb = pd.date_range("2026-02-01", "2026-02-03", freq="D")  # 3 of 28 days: too thin
    days = jan.append(feb)
    buyback = pd.Series(1.0, index=days)
    volume = pd.Series(1_000.0, index=days)
    volume[pd.Timestamp("2026-01-31")] = np.nan  # a day without volume leaves the pair out
    tau = val.monthly_tau(buyback, volume, min_coverage=0.9)
    assert tau.index.tolist() == [pd.Timestamp("2026-01-01")]
    assert tau.iloc[0] == pytest.approx(30 * 1.0 / (30 * 1_000.0))
