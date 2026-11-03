"""Invariants of distribution.json built from the data directory (the snapshot by default)."""

import json
from pathlib import Path

import pandas as pd
import pytest

from capture import manifest as mf
from capture.build import distribution_payload, write_json

FREQS = ("month", "week")


@pytest.fixture(scope="module")
def payload(data_dir: Path) -> dict:
    return distribution_payload(data_dir, "test")


@pytest.fixture(scope="module")
def tables(data_dir: Path) -> dict[str, pd.DataFrame]:
    names = ("explorer_1click_daily", "explorer_channels_daily", "explorer_recipients_daily")
    return {n: pd.read_parquet(data_dir / f"{n}.parquet") for n in names}


def test_payload_is_json_safe(payload: dict) -> None:
    json.dumps(payload, allow_nan=False)


def test_channel_and_asset_shares_add_up_to_one(payload: dict) -> None:
    for freq in FREQS:
        for key in ("channels", "assets"):
            frame = pd.DataFrame(payload[key][freq])
            sums = frame.groupby("period")["share"].sum()
            assert len(sums) > 0
            assert (sums - 1.0).abs().max() <= 1e-6, f"{key}/{freq}: {sums.to_dict()}"
            assert ((frame["share"] >= 0) & (frame["share"] <= 1)).all()


def test_hhi_and_top_share_are_in_range(payload: dict) -> None:
    for freq in FREQS:
        frame = pd.DataFrame(payload["periods"][freq])
        for key in ("channel", "asset"):
            hhi, n = frame[f"hhi_{key}"], frame[f"n_{key}"]
            assert ((hhi >= 0) & (hhi <= 1)).all(), f"{key} HHI outside [0, 1]"
            assert (hhi >= 1 / n - 1e-9).all()  # HHI cannot be below 1/n
            top5, top1 = frame[f"top5_{key}_share"], frame[f"max_{key}_share"]
            assert ((top5 <= 1 + 1e-9) & (top5 >= top1 - 1e-9)).all()
            assert (hhi >= top1**2 - 1e-9).all()


def test_category_shares_stay_within_one(payload: dict) -> None:
    for freq in FREQS:
        frame = pd.DataFrame(payload["periods"][freq])
        for col in (
            "zec_share",
            "stablecoin_share",
            "unmapped_share",
            "near_wallet_only_share",
            "no_app_fee_share",
            "declared_fee_share_to_near",
            "explorer_share_of_defillama_volume",
        ):
            values = frame[col].dropna()
            assert ((values >= 0) & (values <= 1)).all(), col
        parts = frame[["zec_share", "stablecoin_share", "unmapped_share"]].sum(axis=1)
        assert (parts <= 1 + 1e-9).all()  # ZEC and stablecoins never overlap
        near_plus_free = frame["near_wallet_only_share"] + frame["no_app_fee_share"]
        assert (near_plus_free <= 1 + 1e-9).all()


def test_nearly_every_asset_is_mapped_to_a_symbol(payload: dict) -> None:
    for freq in FREQS:
        frame = pd.DataFrame(payload["periods"][freq])
        assert (frame["unmapped_share"] < 0.01).all(), "token list no longer covers the volume"


def test_totals_agree_across_tables_and_periods(payload: dict, tables: dict) -> None:
    daily, channels, recipients = tables.values()
    volume = daily["volume_usd"].sum()
    assert channels["volume_usd"].sum() == pytest.approx(volume)
    for freq in FREQS:
        periods = pd.DataFrame(payload["periods"][freq])
        assert periods["volume_usd"].sum() == pytest.approx(volume)
        assert periods["fee_usd"].sum() == pytest.approx(daily["fee_usd"].sum())
    # fee is additive across recipients; volume is not (a transaction counts in each recipient)
    assert recipients["fee_usd"].sum() == pytest.approx(daily["fee_usd"].sum())
    assert recipients["volume_usd"].sum() >= volume - 1e-6
    assert channels["tx_count"].sum() == daily["tx_count"].sum()


def test_complete_periods_cover_every_day(payload: dict) -> None:
    months = pd.DataFrame(payload["periods"]["month"])
    for row in months.itertuples():
        expected = pd.Period(row.period, "M").days_in_month
        assert row.complete == (row.days == expected)
    weeks = pd.DataFrame(payload["periods"]["week"])
    assert ((weeks["days"] == 7) == weeks["complete"]).all()


def test_attribution_is_a_share_of_revenue_not_a_claim_about_all_of_it(payload: dict) -> None:
    months = pd.DataFrame(payload["periods"]["month"]).dropna(subset=["attributable_share"])
    assert len(months) > 0
    assert (months["attributable_share"] >= 0).all()
    assert (months["declared_fee_near_usd"] <= months["declared_fee_usd"] + 1e-9).all()


def test_scope_and_limits_are_stated(payload: dict) -> None:
    scope = payload["scope"]
    assert scope["explorer_available"] and scope["covers"] == "1Click transactions only"
    assert scope["near_com"]["measured"] is False
    assert any("near.com" in n for n in payload["notes"])
    assert "USDT" in payload["stablecoin_symbols"]
    assert all(i["sha256"] for i in payload["inputs"])


def test_fallback_without_explorer_tables_states_the_limit(tmp_path: Path) -> None:
    llama = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-10-01", "2026-10-02"]).date,
            "volume_usd": [1000.0, 1000.0],
            "fees_usd": [10.0, 20.0],
            "revenue_usd": [1.0, 2.0],
            "holders_revenue_usd": [1.0, 2.0],
        }
    )
    path = tmp_path / "defillama_intents_daily.parquet"
    llama.to_parquet(path, index=False)
    entry = mf.make_entry(tmp_path, path, source="t", pulled_at_utc="2026-11-02T00:00:00Z")
    mf.write_manifest(tmp_path, [entry])
    result = distribution_payload(tmp_path, "test")
    assert result["scope"] == {"explorer_available": False}
    assert result["take_rates"]["monthly"][0]["fees_take_rate"] == pytest.approx(30 / 2000)
    assert "periods" not in result and "only DefiLlama take rates" in result["notes"][0]
    write_json(tmp_path / "out.json", result)  # JSON-safe too
