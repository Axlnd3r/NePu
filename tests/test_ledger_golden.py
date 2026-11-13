"""Golden tests for the ledger functions (waterfall, lever bridge, conditions, markers).

Waterfall over 2 days, worked by hand (price 2 USD on both days):
    volume 1,000,000 + 1,000,000 = 2,000,000 USD
    fees 1,600 + 1,600 = 3,200 USD          -> 16 per 10,000 of volume
    revenue 550 + 550 = 1,100 USD            -> 5.5
    on-chain revenue 275 + 275 NEAR x 2 = 1,100 USD
    buyback wallet 180 + 180 NEAR x 2 = 720 USD -> 3.6
    burn 10 + 10 NEAR x 2 = 40 USD; issuance 1,700 + 1,700 NEAR x 2 = 6,800 USD -> 34
"""

import pandas as pd
import pytest

from capture.models import ledger
from capture.models import valuation as val

D = pd.Timestamp


@pytest.fixture
def daily() -> pd.DataFrame:
    index = pd.date_range("2026-10-29", "2026-10-30", freq="D")
    return pd.DataFrame(
        {
            "volume_usd": 1_000_000.0,
            "fees_usd": 1_600.0,
            "revenue_usd": 550.0,
            "onchain_revenue_near": 275.0,
            "buyback_near": 180.0,
            "burnt_near": 10.0,
            "issuance_gross_near": 1_700.0,
            "near_usd": 2.0,
        },
        index=index,
    )


def test_waterfall_sums_each_step_in_usd(daily: pd.DataFrame) -> None:
    w = ledger.waterfall(daily, end=D("2026-10-30"), days=2)
    assert w["start"] == "2026-10-29" and w["end"] == "2026-10-30" and w["days"] == 2
    assert w["usd"] == pytest.approx(
        {
            "volume": 2_000_000.0,
            "fees": 3_200.0,
            "revenue": 1_100.0,
            "onchain_revenue": 1_100.0,
            "buyback_wallet": 720.0,
            "burn": 40.0,
            "issuance": 6_800.0,
        }
    )
    assert w["per_10k_volume"]["fees"] == pytest.approx(16.0)
    assert w["per_10k_volume"]["buyback_wallet"] == pytest.approx(3.6)
    assert w["per_10k_volume"]["issuance"] == pytest.approx(34.0)


def test_waterfall_reports_what_each_step_keeps(daily: pd.DataFrame) -> None:
    kept = ledger.waterfall(daily, end=D("2026-10-30"), days=2)["kept"]
    assert kept["fees_of_volume"] == pytest.approx(3_200 / 2_000_000)
    assert kept["revenue_of_fees"] == pytest.approx(1_100 / 3_200)
    assert kept["onchain_of_revenue"] == pytest.approx(1.0)
    assert kept["buyback_of_onchain"] == pytest.approx(720 / 1_100)


def test_waterfall_refuses_a_window_with_missing_days(daily: pd.DataFrame) -> None:
    daily.loc[D("2026-10-29"), "buyback_near"] = float("nan")
    with pytest.raises(ValueError, match="missing"):
        ledger.waterfall(daily, end=D("2026-10-30"), days=2)


def test_lever_bridge_multiplies_out_to_the_remaining_volume_multiple() -> None:
    supply, price, burn, v0 = 365e6, 2.0, 1_000.0, 100e6
    steps = ledger.lever_bridge(
        v0, supply, price, burn, tau_buyback=0.0003, tau_revenue=0.0006,
        inflation_now=0.025, inflation_target=0.016,
    )  # fmt: skip
    assert [s["step"] for s in steps] == ["today", "inflation_to_target", "all_revenue_to_buybacks"]
    v_today = val.breakeven_volume(0.025, supply, price, burn, 0.0003)
    v_last = val.breakeven_volume(0.016, supply, price, burn, 0.0006)
    assert steps[0]["volume_multiple"] == pytest.approx(v_today / v0)
    assert steps[-1]["volume_multiple"] == pytest.approx(v_last / v0)
    product = steps[0]["volume_multiple"]
    for s in steps[1:]:
        product /= s["closes_by"]
    assert product == pytest.approx(steps[-1]["volume_multiple"])
    assert steps[2]["closes_by"] == pytest.approx(2.0)  # doubling tau halves V*


def test_conditions_state_value_threshold_and_whether_met() -> None:
    cond = ledger.conditions(
        volume=130e6, v_star=990e6, routed_share=0.655, worst_deviation=0.11, tolerance=0.15
    )
    by = {c["id"]: c for c in cond}
    assert set(by) == {"volume", "routing", "reconciliation"}
    assert by["volume"]["met"] is False and by["volume"]["progress"] == pytest.approx(130 / 990)
    assert by["routing"]["threshold"] == 1.0 and by["routing"]["progress"] == pytest.approx(0.655)
    assert by["reconciliation"]["met"] is False and by["reconciliation"]["effect"] == "withdraw"
    assert by["volume"]["effect"] == "support" and by["routing"]["effect"] == "support"
    triggered = ledger.conditions(130e6, 990e6, 0.655, 0.2, 0.15)
    assert {c["id"]: c["met"] for c in triggered}["reconciliation"] is True


def test_the_two_supporting_conditions_are_not_the_same_condition() -> None:
    """Volume vs V* and take rate vs the take rate needed are one ratio written twice
    (V0 / V* = tau / tau*), so routing is used instead: it moves independently of volume."""
    a = {c["id"]: c["progress"] for c in ledger.conditions(130e6, 990e6, 0.655, 0.11, 0.15)}
    b = {c["id"]: c["progress"] for c in ledger.conditions(260e6, 990e6, 0.655, 0.11, 0.15)}
    assert b["volume"] == pytest.approx(2 * a["volume"]) and b["routing"] == a["routing"]


def test_this_week_compares_with_seven_days_earlier() -> None:
    index = pd.date_range("2026-10-20", "2026-10-31", freq="D")
    cr = pd.Series([0.10 + i * 0.001 for i in range(len(index))], index=index)
    cr[D("2026-11-01")] = float("nan")  # trailing empty day is skipped
    week = ledger.this_week(cr)
    assert week["date"] == "2026-10-31" and week["prev_date"] == "2026-10-24"
    assert week["value"] == pytest.approx(0.111) and week["prev"] == pytest.approx(0.104)
    assert week["sentence"] == "This week: CR 30d = 0.111 (prev 0.104)"


def test_largest_step_down_finds_the_issuance_cut_despite_lumpy_days() -> None:
    index = pd.date_range("2025-10-01", periods=60, freq="D")
    before = [160.0 if i % 4 else 215.0 for i in range(29)]
    after = [81.0 if i % 4 else 107.0 for i in range(31)]
    s = pd.Series(before + after, index=index)
    assert ledger.largest_step_down(s, window=14) == D("2025-10-30")


def test_inflation_path_waits_for_the_grace_period_before_ramping() -> None:
    path = val.inflation_path(60, 0.025, 0.016, ramp_months=24, delay_months=3)
    assert path[:3] == pytest.approx(0.025)  # months 1-3: grace period
    assert path[3] == pytest.approx(0.025 - 0.009 / 24)  # month 4: first step
    assert path[26] == pytest.approx(0.016)  # month 27 = 3 + 24: arrived
    assert path[27:] == pytest.approx(0.016)


def test_step_down_is_dated_to_the_first_day_closer_to_the_new_level() -> None:
    """A change late in a day leaves a transition day between the two levels (as on 2025-10-29)."""
    index = pd.date_range("2025-10-01", periods=60, freq="D")
    values = [160.0] * 28 + [140.0] + [80.0] * 31  # day 29 (2025-10-29) is mostly the old rate
    step = ledger.step_down(pd.Series(values, index=index), window=14)
    assert step["date"] == D("2025-10-30")
    assert step["transition_date"] == D("2025-10-29")
    assert step["before"] == pytest.approx(160.0) and step["after"] == pytest.approx(80.0, rel=0.05)


def test_step_down_without_a_transition_day() -> None:
    index = pd.date_range("2025-10-01", periods=40, freq="D")
    step = ledger.step_down(pd.Series([100.0] * 20 + [50.0] * 20, index=index), window=10)
    assert step["date"] == D("2025-10-21") and step["transition_date"] is None


@pytest.fixture
def three_days() -> pd.DataFrame:
    """Price 2, 4 and 6 USD; 10 NEAR issued, 1 bought back and 0.5 burnt each day."""
    index = pd.date_range("2026-10-28", "2026-10-30", freq="D")
    return pd.DataFrame(
        {
            "issuance_gross_near": 10.0,
            "buyback_near": 1.0,
            "burnt_near": 0.5,
            "near_usd": [2.0, 4.0, 6.0],
        },
        index=index,
    )


def test_price_basis_values_the_gap_at_each_days_price(three_days: pd.DataFrame) -> None:
    out = ledger.price_basis(three_days, D("2026-10-30"), days=3)
    assert out["near_usd_mean"] == pytest.approx(4.0)
    assert out["volume_multiple"] == pytest.approx((10 - 0.5) * 12 / (1 * 12))


def test_price_basis_refuses_a_gap(three_days: pd.DataFrame) -> None:
    gap = three_days.copy()
    gap.loc[D("2026-10-29"), "buyback_near"] = float("nan")
    with pytest.raises(ValueError, match="buyback_near"):
        ledger.price_basis(gap, D("2026-10-30"), days=3)
    with pytest.raises(ValueError):
        ledger.price_basis(three_days, D("2026-10-30"), days=4)


def test_holder_view_identity_and_rates(three_days: pd.DataFrame) -> None:
    out = ledger.holder_view(
        three_days,
        D("2026-10-30"),
        days=3,
        supply=1000.0,
        price=2.0,
        buyback_usd_per_day=1.0,
        inflation=0.0365,
        burnt_near_per_day=0.01,
    )
    assert out["as_of"] == "2026-10-30" and out["near_usd"] == 2.0
    assert out["market_value_usd"] == pytest.approx(2000.0)
    assert out["buyback_revenue_usd_per_year"] == pytest.approx(365.0)
    assert out["value_to_revenue"] == pytest.approx(2000.0 / 365.0)
    assert out["breakeven_value_to_revenue"] == pytest.approx(1 / (0.0365 - 365 * 0.01 / 1000))
    assert out["gross_new_supply_rate"] == pytest.approx(10 * 365 / 1000)
    assert out["net_new_supply_rate"] == pytest.approx((10 - 1 - 0.5) * 365 / 1000)


def test_holder_multiple_over_its_break_even_is_the_volume_multiple(three_days) -> None:
    supply, price, burn, tau, v0, inflation = 1000.0, 2.0, 0.01, 0.001, 500.0, 0.0365
    out = ledger.holder_view(
        three_days,
        D("2026-10-30"),
        days=3,
        supply=supply,
        price=price,
        buyback_usd_per_day=tau * v0,
        inflation=inflation,
        burnt_near_per_day=burn,
    )
    multiple = val.breakeven_volume(inflation, supply, price, burn, tau) / v0
    assert out["value_to_revenue"] / out["breakeven_value_to_revenue"] == pytest.approx(multiple)
