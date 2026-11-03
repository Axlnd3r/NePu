"""Invariants of developer.json built from the data directory (the snapshot by default)."""

import json
from pathlib import Path

import pandas as pd
import pytest

from capture.build import developer_payload
from capture.models import developer as dev


@pytest.fixture(scope="module")
def payload(data_dir: Path) -> dict:
    return developer_payload(data_dir, "test")


@pytest.fixture(scope="module")
def cohorts(payload: dict) -> pd.DataFrame:
    return pd.DataFrame(payload["cohorts"])


def test_payload_is_json_safe(payload: dict) -> None:
    json.dumps(payload, allow_nan=False)


def test_cohort_shares_are_between_zero_and_one(cohorts: pd.DataFrame, payload: dict) -> None:
    strict = pd.DataFrame(payload["cohorts_strict"]["rows"])
    for frame in (cohorts, strict):
        for k in dev.RETENTION_LAGS:
            share = frame[f"share_{k}"].dropna()
            assert ((share >= 0) & (share <= 1)).all(), f"share_{k}"
            retained = frame.dropna(subset=[f"retained_{k}"])
            assert (retained[f"retained_{k}"] <= retained["cohort_size"]).all()
        assert ((frame["top_parent_share"] > 0) & (frame["top_parent_share"] <= 1)).all()


def test_a_stricter_activity_rule_never_raises_retention(
    cohorts: pd.DataFrame, payload: dict
) -> None:
    strict = pd.DataFrame(payload["cohorts_strict"]["rows"]).set_index("cohort")
    base = cohorts.set_index("cohort")
    for k in dev.RETENTION_LAGS:
        both = pd.concat(
            [base[f"share_{k}"], strict[f"share_{k}"]], axis=1, keys=["base", "strict"]
        ).dropna()
        assert (both["strict"] <= both["base"] + 1e-12).all()


def test_later_months_are_empty_exactly_when_they_are_incomplete(
    cohorts: pd.DataFrame, payload: dict
) -> None:
    last_complete = dev._last_complete_month(pd.Timestamp(payload["window"]["last_date"]))
    for row in cohorts.itertuples():
        for k in dev.RETENTION_LAGS:
            observable = pd.Period(row.cohort, "M") + k <= last_complete
            assert not pd.isna(getattr(row, f"share_{k}")) == observable


def test_new_contracts_match_an_independent_count(
    data_dir: Path, payload: dict, cohorts: pd.DataFrame
) -> None:
    contracts = pd.read_parquet(data_dir / "contracts_daily.parquet")
    contracts["date"] = pd.to_datetime(contracts["date"])
    start = contracts["date"].min() + pd.Timedelta(days=payload["window"]["burn_in_days"])
    first_deploy = contracts[contracts["deploys"] > 0].groupby("contract_account")["date"].min()
    first_row = contracts.groupby("contract_account")["date"].min()
    eligible = first_deploy >= start
    existed = first_row.reindex(first_deploy.index) < first_deploy
    expected = first_deploy[eligible & ~existed]
    assert cohorts["cohort_size"].sum() == len(expected)
    ex = payload["exclusions"]
    assert (
        len(expected) + ex["dropped_burn_in"] + ex["dropped_existing"] == ex["deploying_accounts"]
    )


def test_the_test_series_uses_complete_cohorts_only(payload: dict, cohorts: pd.DataFrame) -> None:
    complete = {pd.Period(c, "M") + 1 for c in cohorts.loc[cohorts["complete"], "cohort"]}
    series = pd.DataFrame(payload["monthly_series"]).dropna(subset=["retained_new_contracts"])
    assert {pd.Period(m, "M") for m in series["month"]} <= complete
    assert not cohorts.loc[
        ~cohorts["complete"], "cohort"
    ].empty  # first and last cohorts are cut short


def test_lead_lag_rows_are_valid_and_cover_every_requested_lag(payload: dict) -> None:
    rows = pd.DataFrame(payload["lead_lag"]["rows"])
    assert set(rows["lag"]) == set(dev.LAGS) and set(rows["sample"]) == {"train", "test"}
    shown = rows.dropna(subset=["pearson"])
    assert ((shown["pearson"] >= -1) & (shown["pearson"] <= 1)).all()
    assert ((shown["p_value"] >= 0) & (shown["p_value"] <= 1)).all()
    assert (shown["n"] >= dev.MIN_PAIRS).all()
    assert rows.loc[rows["pearson"].isna(), "note"].notna().all()  # every gap says why


def test_verdict_is_one_of_three_outcomes_and_never_causal(payload: dict) -> None:
    verdict = payload["lead_lag"]["verdict"]
    assert verdict["result"] in {"null", "association", "insufficient_data"}
    text = verdict["text"].lower()
    for forbidden in ("causes", "drives", "leads to", "because", "results in"):
        assert forbidden not in text
    assert any("does not show cause" in note for note in payload["notes"])
