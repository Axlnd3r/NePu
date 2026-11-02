"""Golden test: a hand-made 3-day fixture whose expected values are computed by hand.

Fixture (day 0 only provides the previous supply; the window is days 1..3, window = 3):

    day            0      1      2      3
    total_supply   1000   1010   1021   1033
    burnt_near     0      1      2      3
    near_usd       2      2      2      4
    chg_buybacks   -      +4     +6     +8      (net daily change of the buyback wallet)
    chg_1cs        -      0      -5     0       (1csfundsadmin falls by 5 on day 2)
    chg_fefunds    -      0      0      0
    revenue_usd    -      1      2      3
    volume_usd     -      1000   2000   3000
    holders_usd    -      4      4      12

By hand:
    issuance_gross = diff(supply) + burnt           = 10+1, 11+2, 12+3   = 11, 13, 15   (sum 39)
    transfer in    = day 2: 1cs fell 5, buybacks rose 6 -> min(5, 6) = 5; other days 0
    buyback_near   = 4, 6-5, 8                      = 4, 1, 8            (sum 13)
    CR_float       = (13 + 6) / 39                  = 19/39              = 0.487179...
    CR_supply      = 6 / 39                         = 0.153846...
    CR_float_usd   = ((4+1)*2 + (1+2)*2 + (8+3)*4) / (11*2 + 13*2 + 15*4) = 60/108 = 0.5555...
    tau_eff        = (1+2+3) / (1000+2000+3000)     = 0.001
    proxy_near     = 4/2, 4/2, 12/4                 = 2, 2, 3            (sum 7)
    CR_float_proxy = (7 + 6) / 39                   = 1/3
    V*             = (avg issuance 13 * price 4 - avg burnt_usd (2+4+12)/3 = 6) / 0.001
                   = (52 - 6) / 0.001               = 46,000
    On day 2 the window needs day 0's issuance, which does not exist, so every ratio is empty.
"""

import numpy as np
import pandas as pd
import pytest

from capture.models import breakeven, coverage

NAN = np.nan


@pytest.fixture
def inputs() -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=4, freq="D", name="date")
    return pd.DataFrame(
        {
            "total_supply_near": [1000.0, 1010.0, 1021.0, 1033.0],
            "burnt_near": [0.0, 1.0, 2.0, 3.0],
            "near_usd": [2.0, 2.0, 2.0, 4.0],
            "chg_buybacks": [NAN, 4.0, 6.0, 8.0],
            "chg_1csfundsadmin": [NAN, 0.0, -5.0, 0.0],
            "chg_fefundsadmin": [NAN, 0.0, 0.0, 0.0],
            "revenue_usd": [NAN, 1.0, 2.0, 3.0],
            "volume_usd": [NAN, 1000.0, 2000.0, 3000.0],
            "holders_revenue_usd": [NAN, 4.0, 4.0, 12.0],
        },
        index=idx,
    )


def test_golden_coverage_ratios(inputs: pd.DataFrame) -> None:
    table = coverage.coverage_table(inputs, windows=(3,))
    assert table["issuance_gross_near"].tolist()[1:] == [11.0, 13.0, 15.0]
    assert table["buyback_near"].tolist()[1:] == [4.0, 1.0, 8.0]
    last = table.iloc[-1]
    assert last["cr_float_3"] == pytest.approx(19 / 39)
    assert last["cr_supply_3"] == pytest.approx(6 / 39)
    assert last["cr_float_usd_3"] == pytest.approx(60 / 108)
    assert last["cr_float_proxy_3"] == pytest.approx(13 / 39)
    assert last["tau_eff_3"] == pytest.approx(0.001)
    assert table["cr_float_3"].iloc[:3].isna().all()  # day 2 would need day 0's issuance


def test_golden_v_star(inputs: pd.DataFrame) -> None:
    table = coverage.coverage_table(inputs, windows=(3,))
    v = breakeven.v_star(
        table["issuance_gross_near"],
        table["burnt_near"],
        table["near_usd"],
        table["tau_eff_3"],
        window=3,
    )
    assert v.iloc[-1] == pytest.approx(46_000.0)
    assert v.iloc[:3].isna().all()


def test_transfer_netting_only_counts_transfers_into_the_buyback_wallet() -> None:
    changes = pd.DataFrame(
        {
            "chg_buybacks": [4.0, -6.0, 3.0, 5.0],
            "chg_1csfundsadmin": [0.0, 0.0, -0.5, -2.0],
            "chg_fefundsadmin": [0.0, 2.0, 0.0, 0.0],
        }
    )
    # day 1: the buyback wallet itself fell -> no transfer in, nothing received
    # day 2: 1cs fell by 0.5 (< 1 NEAR threshold) -> not a transfer
    # day 3: 1cs fell by 2, buybacks rose by 5 -> 2 NEAR are an internal transfer
    assert coverage.internal_transfers_in(changes).tolist() == [0.0, 0.0, 0.0, 2.0]
    assert coverage.buyback_near(changes).tolist() == [4.0, 0.0, 3.0, 3.0]


def test_empty_when_window_has_no_revenue(inputs: pd.DataFrame) -> None:
    inputs["revenue_usd"] = 0.0
    table = coverage.coverage_table(inputs, windows=(3,))
    assert table["tau_eff_3"].isna().all()  # undefined, not zero
    v = breakeven.v_star(
        table["issuance_gross_near"],
        table["burnt_near"],
        table["near_usd"],
        table["tau_eff_3"],
        window=3,
    )
    assert v.isna().all()


def test_sensitivity_grid_shape_and_scaling() -> None:
    grid = breakeven.sensitivity_grid(
        total_supply_near=1000.0, near_usd=2.0, burnt_near_avg=0.0, tau=0.001
    )
    assert len(grid) == 2 * 3 * 3
    base = grid[
        (grid.inflation == 0.025) & (grid.price_multiplier == 1.0) & (grid.tau_multiplier == 1.0)
    ]
    # 2.5% of 1000 NEAR a year = 0.0684932 NEAR/day x 2 USD / 0.001
    assert base["v_star_usd_per_day"].iloc[0] == pytest.approx(0.025 * 1000 / 365 * 2 / 0.001)
    double_tau = grid[
        (grid.inflation == 0.025) & (grid.price_multiplier == 1.0) & (grid.tau_multiplier == 1.5)
    ]
    assert double_tau["v_star_usd_per_day"].iloc[0] == pytest.approx(
        base["v_star_usd_per_day"].iloc[0] / 1.5
    )
    low = grid[
        (grid.inflation == 0.016) & (grid.price_multiplier == 1.0) & (grid.tau_multiplier == 1.0)
    ]
    assert low["v_star_usd_per_day"].iloc[0] == pytest.approx(
        base["v_star_usd_per_day"].iloc[0] * 0.016 / 0.025
    )


def test_burn_above_issuance_gives_zero_not_negative() -> None:
    grid = breakeven.sensitivity_grid(
        total_supply_near=1000.0, near_usd=2.0, burnt_near_avg=1.0, tau=0.001
    )
    assert (grid["v_star_usd_per_day"] == 0.0).all()
