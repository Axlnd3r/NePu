"""Invariants of the coverage model on the committed snapshot (offline)."""

import numpy as np
import pandas as pd
import pytest

from capture.build import load_tables
from capture.config import DATA_SNAPSHOT
from capture.models import coverage

WINDOWS = coverage.WINDOWS


@pytest.fixture(scope="module")
def inputs() -> pd.DataFrame:
    return coverage.build_inputs(load_tables(DATA_SNAPSHOT))


@pytest.fixture(scope="module")
def table(inputs: pd.DataFrame) -> pd.DataFrame:
    return coverage.coverage_table(inputs)


def _ratio_columns(table: pd.DataFrame) -> list[str]:
    return [c for c in table.columns if c.startswith(("cr_float", "cr_supply"))]


def test_coverage_ratios_are_never_negative_or_infinite(table: pd.DataFrame) -> None:
    for col in _ratio_columns(table):
        values = table[col].dropna()
        assert len(values) > 0, f"{col} has no values at all"
        assert np.isfinite(values).all(), col
        assert (values >= 0).all(), f"{col} has negative values"


def test_float_ratio_is_at_least_supply_ratio(table: pd.DataFrame) -> None:
    """Buybacks are never negative, so adding them cannot lower the ratio."""
    for w in WINDOWS:
        both = table[[f"cr_float_{w}", f"cr_supply_{w}"]].dropna()
        assert (both[f"cr_float_{w}"] >= both[f"cr_supply_{w}"] - 1e-12).all(), w


def test_tau_eff_is_between_zero_and_one_percent(table: pd.DataFrame) -> None:
    for w in WINDOWS:
        values = table[f"tau_eff_{w}"].dropna()
        assert len(values) > 0
        assert (values > 0).all() and (values < 0.01).all(), (
            f"tau_eff_{w}: {values.min()}..{values.max()}"
        )


def test_annualised_gross_issuance_after_2025_10_30_is_between_1_5_and_3_percent(
    table: pd.DataFrame,
) -> None:
    after = table.loc["2025-10-31":].dropna(subset=["issuance_gross_near"])
    days = len(after)
    assert days > 300
    annualised = after["issuance_gross_near"].sum() / after["total_supply_near"].mean() * 365 / days
    assert 0.015 <= annualised <= 0.03, f"annualised issuance {annualised:.4%}"


def _window_complete(frame: pd.DataFrame, columns: list[str], window: int) -> pd.Series:
    ok = frame[columns].notna().all(axis=1)
    return ok.rolling(window, min_periods=window).sum() == window


def test_no_empty_value_on_days_that_have_all_inputs(
    inputs: pd.DataFrame, table: pd.DataFrame
) -> None:
    """A ratio is empty exactly when some day of its window lacks an input, never otherwise."""
    for w in WINDOWS:
        base = table[["issuance_gross_near", "burnt_near"]]
        supply_ok = _window_complete(base, ["issuance_gross_near", "burnt_near"], w)
        pd.testing.assert_series_equal(
            table[f"cr_supply_{w}"].notna(),
            supply_ok,
            check_names=False,
            obj=f"cr_supply_{w} availability",
        )
        float_ok = _window_complete(table, ["issuance_gross_near", "burnt_near", "buyback_near"], w)
        pd.testing.assert_series_equal(
            table[f"cr_float_{w}"].notna(),
            float_ok,
            check_names=False,
            obj=f"cr_float_{w} availability",
        )
        usd_ok = _window_complete(
            table, ["issuance_gross_near", "burnt_near", "buyback_near", "near_usd"], w
        )
        pd.testing.assert_series_equal(
            table[f"cr_float_usd_{w}"].notna(),
            usd_ok,
            check_names=False,
            obj=f"cr_float_usd_{w} availability",
        )
        tau_ok = _window_complete(inputs, ["revenue_usd", "volume_usd"], w)
        revenue_positive = inputs["revenue_usd"].rolling(w, min_periods=w).sum() > 0
        pd.testing.assert_series_equal(
            table[f"tau_eff_{w}"].notna(),
            tau_ok & revenue_positive,
            check_names=False,
            obj=f"tau_eff_{w} availability",
        )


def test_buyback_series_starts_after_the_wallet_first_appears(table: pd.DataFrame) -> None:
    first = table["buyback_near"].first_valid_index()
    assert first is not None and first >= pd.Timestamp("2026-04-26")
    assert (table["buyback_near"].dropna() >= 0).all()
