"""Valuation Lab on the committed snapshot: invariants of the Monte Carlo output (F5 DoD)."""

import json
import math

import numpy as np
import pytest

from capture import build, config
from capture.models import coverage
from capture.models import valuation as val

SOURCE = "snapshot"


@pytest.fixture(scope="module")
def payload(data_dir) -> dict:
    return build.valuation_payload(data_dir, SOURCE)


def _runs(payload: dict, scenario: str) -> dict[tuple[str, float], dict]:
    return {
        (r["inflation_path"], r["price_multiplier"]): r
        for r in payload["scenarios"]
        if r["scenario"] == scenario
    }


def test_every_probability_is_between_zero_and_one(payload: dict) -> None:
    assert payload["scenarios"]
    for run in payload["scenarios"]:
        for p in [*run["p_cr_ge_1"].values(), run["share_reaching_by_60"]]:
            assert 0.0 <= p <= 1.0


def test_each_scenario_is_run_for_both_inflation_paths_and_three_prices(payload: dict) -> None:
    assert len(payload["scenarios"]) == 3 * 2 * 3
    assert {r["price_multiplier"] for r in payload["scenarios"]} == {0.5, 1.0, 2.0}
    assert {r["inflation_path"] for r in payload["scenarios"]} == {"constant_2.5", "ramp_to_1.6"}
    for run in payload["scenarios"]:
        assert set(run["p_cr_ge_1"]) == {"12", "36", "60"}
        assert len(run["fan"]["p50"]) == config.MC_MONTHS


def test_same_seed_gives_identical_output(data_dir, payload: dict) -> None:
    again = build.valuation_payload(data_dir, SOURCE)
    assert json.dumps(again, sort_keys=True) == json.dumps(payload, sort_keys=True)
    other = build.valuation_payload(data_dir, SOURCE, seed=config.RANDOM_SEED + 1)
    assert json.dumps(other["scenarios"]) != json.dumps(payload["scenarios"])


def _first(run: dict) -> float:
    m = run["median_first_month"]
    return math.inf if m == "not reached" else m


def test_flat_is_never_more_optimistic_than_historical_on_the_median(payload: dict) -> None:
    hist, flat = _runs(payload, "historical"), _runs(payload, "flat")
    assert hist.keys() == flat.keys()
    for key, a in hist.items():
        c = flat[key]
        assert all(
            pc <= pa + 1e-12 for pc, pa in zip(c["fan"]["p50"], a["fan"]["p50"], strict=True)
        )
        assert _first(c) >= _first(a)


def test_decay_sits_between_flat_and_historical_on_the_median(payload: dict) -> None:
    hist, decay, flat = (_runs(payload, s) for s in ("historical", "decay", "flat"))
    for key in hist:
        for pa, pb, pc in zip(
            hist[key]["fan"]["p50"], decay[key]["fan"]["p50"], flat[key]["fan"]["p50"], strict=True
        ):
            assert pc - 1e-12 <= pb <= pa + 1e-12


def test_a_lower_price_never_lowers_cr_with_the_buyback_in_usd(payload: dict) -> None:
    """Buyback USD is tau x volume, so fewer USD per NEAR means more NEAR bought per NEAR issued."""
    for scenario in val.SCENARIOS:
        runs = _runs(payload, scenario)
        for path in ("constant_2.5", "ramp_to_1.6"):
            low, mid, high = (runs[(path, m)]["fan"]["p50"] for m in (0.5, 1.0, 2.0))
            assert all(a >= b >= c for a, b, c in zip(low, mid, high, strict=True))


def test_the_lower_inflation_path_is_never_less_favourable(payload: dict) -> None:
    for scenario in val.SCENARIOS:
        runs = _runs(payload, scenario)
        for m in (0.5, 1.0, 2.0):
            flat_rate, ramp = runs[("constant_2.5", m)], runs[("ramp_to_1.6", m)]
            assert all(
                r >= f - 1e-12
                for r, f in zip(ramp["fan"]["p50"], flat_rate["fan"]["p50"], strict=True)
            )


def test_price_is_stated_as_constant_and_no_price_target_appears(payload: dict) -> None:
    text = json.dumps(payload).lower()
    assert "held constant" in payload["assumptions"]["price"].lower()
    assert "not a forecast" in payload["assumptions"]["price"].lower()
    assert "price target" not in text and "target price" not in text


def test_reverse_table_covers_horizons_inflation_and_both_tau_bases(payload: dict) -> None:
    rows = payload["reverse"]["rows"]
    assert len(rows) == 3 * 2 * 2
    assert {r["horizon_years"] for r in rows} == {1, 3, 5}
    shorter_needs_more = {(r["inflation"], r["basis"]): [] for r in rows}
    for r in sorted(rows, key=lambda r: r["horizon_years"]):
        shorter_needs_more[(r["inflation"], r["basis"])].append(r["required_cagr"])
    for series in shorter_needs_more.values():
        assert series == sorted(series, reverse=True)  # a shorter horizon needs faster growth


def test_the_start_of_the_model_agrees_with_the_measured_cr_float(data_dir, payload: dict) -> None:
    start = payload["start"]
    # Month 0 at the window's own mean price reproduces the measurement (buyback is USD / price).
    assert start["cr_model_month0_at_window_price"] == pytest.approx(
        start["cr_float_30_observed"], rel=0.05
    )
    # At the latest price it differs, and by the price move only: USD buys fewer or more NEAR.
    ratio = start["near_usd"] / start["near_usd_window_mean"]
    assert (start["cr_model_month0"] > start["cr_float_30_observed"]) == (ratio < 1.0)
    inputs = coverage.build_inputs(build.load_tables(data_dir))
    assert start["as_of"] <= inputs["volume_usd"].last_valid_index().date().isoformat()


def test_the_growth_sample_and_its_limits_are_reported(payload: dict) -> None:
    growth = payload["growth"]
    assert growth["n_months"] == len(growth["rows"]) >= 12
    assert growth["first_month"] == "2025-07"
    assert growth["mean_after_launch"] < growth["mean_all"]  # the launch phase dominates the drift
    assert growth["n_blocks_available"] == growth["n_months"] - config.MC_BLOCK_MONTHS + 1


def test_run_scenarios_is_deterministic_and_seed_dependent() -> None:
    inputs = val.Inputs(1e8, 365e6, 2.0, 1_000.0, 0.0002, 0.0004)
    growth = np.array([0.1, -0.05, 0.2, 0.0, -0.1, 0.15])
    paths = {"constant_2.5": val.inflation_path(24, 0.025)}
    kwargs = dict(n_paths=300, n_months=24, block=3, half_life_months=12, inflation_paths=paths)
    a = val.run_scenarios(inputs, growth, seed=7, **kwargs)
    b = val.run_scenarios(inputs, growth, seed=7, **kwargs)
    c = val.run_scenarios(inputs, growth, seed=8, **kwargs)
    assert a == b and a != c
    assert len(a) == 3 * 1 * 3


def test_every_run_reports_the_median_volume_it_implies() -> None:
    """A probability of 1 means little if the volume behind it is absurd; show that volume."""
    inputs = val.Inputs(1e8, 365e6, 2.0, 1_000.0, 0.0002, 0.0004)
    growth = np.array([0.1, -0.05, 0.2, 0.0, -0.1, 0.15])  # mean +0.05 a month
    paths = {"constant_2.5": val.inflation_path(24, 0.025)}
    runs = val.run_scenarios(
        inputs, growth, seed=7, n_paths=500, n_months=24, block=3, half_life_months=12,
        inflation_paths=paths,
    )  # fmt: skip
    by = {(r["scenario"], r["price_multiplier"]): r for r in runs}
    for run in runs:
        assert set(run["volume_p50_usd_per_day"]) == {"12"}  # only the check months inside 24
    for m in (0.5, 1.0, 2.0):
        hist, flat = by[("historical", m)], by[("flat", m)]
        assert hist["volume_p50_usd_per_day"]["12"] > flat["volume_p50_usd_per_day"]["12"]
        assert flat["volume_p50_usd_per_day"]["12"] == pytest.approx(1e8, rel=0.3)


def test_the_payload_shows_the_volume_behind_the_historical_scenario(payload: dict) -> None:
    hist = _runs(payload, "historical")[("constant_2.5", 1.0)]
    flat = _runs(payload, "flat")[("constant_2.5", 1.0)]
    assert hist["volume_p50_usd_per_day"]["60"] > 100 * flat["volume_p50_usd_per_day"]["60"]
    assert any("launch" in n.lower() for n in payload["notes"])
    assert any("range" in n.lower() and "tau" in n.lower() for n in payload["notes"])
