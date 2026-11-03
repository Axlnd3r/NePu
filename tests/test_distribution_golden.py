"""Golden tests for the Distribution Map functions on tiny hand-made tables.

Channels, volume in USD (two days, two months):
    2026-09-30   A 50   B 30   C 20            -> shares .5 .3 .2   HHI = .25 + .09 + .04 = .38
    2026-10-01   A 10   B 10   (none) 80       -> shares .1 .1 .8   HHI = .01 + .01 + .64 = .66
Top-5 share is 1 for both (at most five channels). Keeping the 2 largest per period and folding
the rest into "(other)" leaves 2026-10 as (none) .8, one of A/B .1, (other) .1: still adding to 1.
"""

import pandas as pd
import pytest

from capture.models import distribution as dist

D = pd.Timestamp


@pytest.fixture
def channels() -> pd.DataFrame:
    rows = [
        ("2026-09-30", "A", 50.0), ("2026-09-30", "B", 30.0), ("2026-09-30", "C", 20.0),
        ("2026-10-01", "A", 10.0), ("2026-10-01", "B", 10.0), ("2026-10-01", "(none)", 80.0),
    ]  # fmt: skip
    return pd.DataFrame(
        [
            {"date": D(d), "referral": r, "volume_usd": v, "fee_usd": v / 100, "tx_count": 1}
            for d, r, v in rows
        ]
    )


def test_shares_hhi_and_top_share(channels: pd.DataFrame) -> None:
    shares = dist.volume_shares(channels, "referral", "month")
    assert shares.groupby("period")["share"].sum().tolist() == pytest.approx([1.0, 1.0])
    conc = dist.concentration(shares, "channel").set_index("period")
    assert conc.loc["2026-09", "hhi_channel"] == pytest.approx(0.38)
    assert conc.loc["2026-10", "hhi_channel"] == pytest.approx(0.66)
    assert conc.loc["2026-09", "top5_channel_share"] == pytest.approx(1.0)
    assert conc.loc["2026-10", "max_channel_share"] == pytest.approx(0.8)
    assert conc["n_channel"].tolist() == [3, 3]


def test_hhi_bounds() -> None:
    assert dist.hhi(pd.Series([1.0])) == pytest.approx(1.0)  # one channel owns everything
    assert dist.hhi(pd.Series([0.25] * 4)) == pytest.approx(0.25)  # four equal channels: 1/n


def test_top_with_other_keeps_shares_adding_to_one(channels: pd.DataFrame) -> None:
    shares = dist.volume_shares(channels, "referral", "month")
    top = dist.top_with_other(shares, "referral", 2)
    assert top.groupby("period")["share"].sum().tolist() == pytest.approx([1.0, 1.0])
    october = top[top["period"] == "2026-10"].set_index("referral")
    assert october.loc["(none)", "share"] == pytest.approx(0.8)
    assert october.loc["(other)", "share"] == pytest.approx(0.1)
    assert len(top[top["period"] == "2026-09"]) == 3  # A, B and (other) = C


def test_weekly_periods_start_on_monday_and_flag_partial_weeks() -> None:
    dates = pd.Series(pd.to_datetime(["2026-10-03", "2026-10-04", "2026-10-05"]))  # Sat, Sun, Mon
    assert dist.period_of(dates, "week").tolist() == ["2026-09-28", "2026-09-28", "2026-10-05"]
    table = dist.period_table(["2026-09-28", "2026-10-05"], "week", "2026-10-03", "2026-10-11")
    assert table["days"].tolist() == [2, 7] and table["complete"].tolist() == [False, True]
    months = dist.period_table(["2026-10", "2026-11"], "month", "2026-10-03", "2026-11-01")
    assert months["days"].tolist() == [29, 1] and months["complete"].tolist() == [False, False]


def test_asset_categories_zec_stablecoins_and_unmapped() -> None:
    tokens = pd.DataFrame(
        {
            "asset_id": ["z", "t", "c"],
            "symbol": ["ZEC", "USDT", "USDC"],
            "blockchain": ["zec", "eth", "eth"],
            "decimals": [8, 6, 6],
        }
    )
    daily = pd.DataFrame(
        {
            "date": [D("2026-10-01")] * 4,
            "asset_in": ["z", "t", "c", "mystery"],
            "volume_usd": [20.0, 40.0, 30.0, 10.0],
            "fee_usd": [0.0] * 4,
            "tx_count": [1] * 4,
        }
    )
    by_symbol = dist.volume_shares(dist.symbols(daily, tokens), "symbol", "month")
    cats = dist.asset_categories(by_symbol).iloc[0]
    assert cats["zec_share"] == pytest.approx(0.2)
    assert cats["stablecoin_share"] == pytest.approx(0.7)  # USDT + USDC
    assert cats["unmapped_share"] == pytest.approx(0.1)
    conc = dist.concentration(by_symbol, "asset").iloc[0]
    assert conc["hhi_asset"] == pytest.approx(0.2**2 + 0.4**2 + 0.3**2 + 0.1**2)


def test_near_wallet_proxy_is_not_called_near_com() -> None:
    daily = pd.DataFrame(
        {
            "date": [D("2026-10-01")] * 4,
            "affiliate": [
                "buybacks.multisignature.near",
                "buybacks.multisignature.near,fefundsadmin.sputnik-dao.near",
                "buybacks.multisignature.near,lifi_int.near",
                "",
            ],
            "volume_usd": [30.0, 10.0, 50.0, 10.0],
        }
    )
    shares = dist.near_wallet_shares(daily, "month").iloc[0]
    assert shares["near_wallet_only_share"] == pytest.approx(0.4)  # first two rows only
    assert shares["no_app_fee_share"] == pytest.approx(0.1)


def test_near_attribution_against_on_chain_revenue() -> None:
    recipients = pd.DataFrame(
        {
            "date": [D("2026-10-01"), D("2026-10-01"), D("2026-10-02")],
            "recipient": ["buybacks.multisignature.near", "swapkit.near", "swapkit.near"],
            "fee_usd": [5.0, 40.0, 5.0],
        }
    )
    onchain = pd.Series([10.0, 10.0], index=pd.to_datetime(["2026-10-01", "2026-10-02"]))
    row = dist.near_attribution(recipients, onchain, "month").iloc[0]
    assert row["declared_fee_near_usd"] == pytest.approx(5.0)
    assert row["declared_fee_share_to_near"] == pytest.approx(5 / 50)
    assert row["attributable_share"] == pytest.approx(5 / 20)


def test_take_rates_use_only_days_with_all_three_values() -> None:
    llama = pd.DataFrame(
        {
            "date": [D("2026-10-01"), D("2026-10-02"), D("2026-10-03")],
            "volume_usd": [1000.0, 1000.0, 5000.0],
            "fees_usd": [10.0, 20.0, None],  # day 3 has no fees: it must not enter the volume total
            "revenue_usd": [1.0, 2.0, 3.0],
        }
    )
    row = dist.take_rates(llama).iloc[0]
    assert row["volume_usd"] == pytest.approx(2000.0)
    assert row["fees_take_rate"] == pytest.approx(30 / 2000)
    assert row["revenue_take_rate"] == pytest.approx(3 / 2000)
    assert row["days"] == 2 and not row["complete"]
