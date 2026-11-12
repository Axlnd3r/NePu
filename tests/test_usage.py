"""usage.json built from the snapshot: what the Network usage page and THESIS.md read (F8)."""

import json

import pandas as pd
import pytest

from capture import build

SOURCE = "snapshot"


@pytest.fixture(scope="module")
def payload(data_dir) -> dict:
    return build.usage_payload(data_dir, SOURCE)


def test_payload_is_json_safe_and_names_its_inputs(payload) -> None:
    json.dumps(payload, allow_nan=False)
    assert {i["path"] for i in payload["inputs"]} == {
        "network_daily.parquet",
        "intents_onchain_daily.parquet",
        "defillama_intents_daily.parquet",
        "price_daily.parquet",
    }


def test_every_week_is_complete_and_inside_the_window(payload) -> None:
    weeks = [pd.Timestamp(w["week"]) for w in payload["weekly"]]
    assert all(w.day_of_week == 0 for w in weeks) and weeks == sorted(weeks)
    assert payload["halves"]["weeks"] == len(weeks)
    assert weeks[0] >= pd.Timestamp(payload["window"]["first_date"])
    assert weeks[-1] + pd.Timedelta(days=6) <= pd.Timestamp(payload["window"]["last_date"])


def test_shares_are_fractions(payload) -> None:
    assert 0 < payload["shares"]["intents_call_share"] < 1
    assert 0 < payload["shares"]["intents_signer_share"] < 1


def test_lead_lag_covers_every_metric_predictor_sample_and_lag(payload) -> None:
    rows = payload["lead_lag"]["rows"]
    assert len(rows) == 2 * 2 * 2 * 4
    assert payload["lead_lag"]["split_week"] == build.USAGE_SPLIT_WEEK
    verdict = payload["lead_lag"]["verdict"]
    assert verdict["result"] in {"supported", "not_supported", "insufficient_data"}
    assert verdict["text"]


def test_the_notes_say_what_the_series_are_and_that_the_test_is_not_blind(payload) -> None:
    notes = " ".join(payload["notes"]).lower()
    assert "signer" in notes and "relayer" in notes
    assert "exploratory" in notes
    assert "cause" in notes
