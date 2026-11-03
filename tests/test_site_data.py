"""Site payloads built from the snapshot: summary, queries, provenance, markers (F6).

These are what the dashboard reads; every number in them must trace back to data/ (rule 1).
"""

import hashlib
import json

import pandas as pd
import pytest

from capture import build, config
from capture import manifest as mf
from capture.models import coverage

SOURCE = "snapshot"


@pytest.fixture(scope="module")
def cov(data_dir) -> dict:
    return build.coverage_payload(data_dir, SOURCE)


@pytest.fixture(scope="module")
def summary(data_dir) -> dict:
    return build.summary_payload(data_dir, SOURCE)


@pytest.fixture(scope="module")
def valuation(data_dir) -> dict:
    return build.valuation_payload(data_dir, SOURCE, n_paths=200)


def test_hero_sentence_states_the_cents_and_matches_coverage(summary: dict, cov: dict) -> None:
    hero = summary["hero"]
    series = {r["date"]: r for r in cov["series"]}
    assert hero["cr_float_usd_30"] == pytest.approx(series[hero["date"]]["cr_float_usd_30"])
    assert hero["cr_float_30"] == pytest.approx(cov["latest"]["cr_float_30"]["value"])
    cents = round(hero["cr_float_usd_30"] * 100)
    assert f"{cents} cents" in hero["sentence"] and hero["date"] in hero["sentence"]


def test_this_week_compares_with_seven_days_earlier(summary: dict) -> None:
    week = summary["this_week"]
    gap = pd.Timestamp(week["date"]) - pd.Timestamp(week["prev_date"])
    assert gap == pd.Timedelta(days=7)
    assert week["sentence"].startswith("This week: CR 30d = ")


def test_ledger_reproduces_cr_float_usd_on_the_same_window(summary: dict, cov: dict) -> None:
    led = summary["ledger"]
    usd = led["usd"]
    series = {r["date"]: r for r in cov["series"]}
    expected = series[led["end"]]["cr_float_usd_30"]
    assert (usd["buyback_wallet"] + usd["burn"]) / usd["issuance"] == pytest.approx(expected)
    assert usd["volume"] > usd["fees"] > usd["revenue"] > usd["buyback_wallet"] > 0
    assert usd["onchain_revenue"] == pytest.approx(
        usd["revenue"], rel=coverage.RECONCILIATION_TOLERANCE
    )


def test_ledger_and_levers_start_where_the_valuation_lab_starts(
    summary: dict, valuation: dict
) -> None:
    start = valuation["start"]
    assert summary["ledger"]["end"] == start["as_of"]
    levers = summary["levers"]["steps"]
    rows = {(r["inflation"], r["basis"]): r for r in valuation["reverse"]["rows"]}
    v0 = start["volume_usd_per_day"]
    today = rows[(config.INFLATION_CURRENT, "buyback")]["breakeven_volume_usd_per_day"]
    last = rows[(config.INFLATION_PROPOSAL, "revenue")]["breakeven_volume_usd_per_day"]
    assert levers[0]["volume_multiple"] == pytest.approx(today / v0)
    assert levers[-1]["volume_multiple"] == pytest.approx(last / v0)
    assert "price" in summary["levers"]["note"].lower()


def test_three_conditions_with_the_reconciliation_guard(summary: dict, cov: dict) -> None:
    cond = {c["id"]: c for c in summary["conditions"]}
    assert set(cond) == {"volume", "routing", "reconciliation"}
    kept = summary["ledger"]["kept"]["buyback_of_onchain"]
    assert cond["routing"]["value"] == pytest.approx(kept)
    worst = max(abs(m["deviation"]) for m in cov["reconciliation"]["months"])
    assert cond["reconciliation"]["value"] == pytest.approx(worst)
    assert cond["reconciliation"]["threshold"] == coverage.RECONCILIATION_TOLERANCE
    for c in cond.values():
        assert isinstance(c["met"], bool) and c["progress"] >= 0


def test_every_bigquery_table_ships_its_sql_text_and_hash(data_dir) -> None:
    queries = {q["id"]: q for q in build.queries_payload(data_dir)["queries"]}
    for entry in mf.read_manifest(data_dir):
        table = entry.path.removesuffix(".parquet")
        q = queries[table]
        if entry.query_file:
            assert q["kind"] == "bigquery_sql"
            text = (config.ROOT / entry.query_file).read_text(encoding="utf-8")
            assert q["text"] == text and q["sha256"] == entry.query_sha256
        else:
            assert q["kind"] in {"http_api", "derived"} and q["text"]


def test_provenance_lists_every_file_with_its_hash_prefix(data_dir) -> None:
    prov = build.provenance_payload(data_dir, SOURCE)
    files = {s["path"]: s for s in prov["sources"]}
    for entry in mf.read_manifest(data_dir):
        assert files[entry.path]["sha256_8"] == entry.sha256[:8]
    assert "events.csv" in {s["path"] for s in prov["reference"]}
    assert prov["manifest_sha256"] == mf.sha256_file(data_dir / "manifest.json")


def test_the_committed_proof_is_for_this_snapshot_and_names_its_network(data_dir) -> None:
    prov = build.provenance_payload(data_dir, SOURCE)
    proof = prov["proof"]
    assert proof["status"] == "committed"
    assert proof["network"] == "testnet"  # never shown as mainnet
    assert proof["manifest_sha256"] == prov["manifest_sha256"]
    assert proof["current"] is True
    assert proof["explorer_url"].startswith("https://explorer.testnet.near.org/transactions/")


def test_the_snapshot_manifest_is_served_byte_for_byte(tmp_path, data_dir) -> None:
    written = {p.name: p for p in build.build(SOURCE, tmp_path)}
    served = written["snapshot-manifest.json"].read_bytes()
    assert served == (data_dir / "manifest.json").read_bytes()
    assert hashlib.sha256(served).hexdigest() == mf.sha256_file(data_dir / "manifest.json")


def test_markers_are_dated_sourced_and_inside_the_data(data_dir, cov: dict) -> None:
    payload = build.markers_payload(data_dir)
    markers = payload["markers"]
    dates = [r["date"] for r in cov["series"]]
    for m in markers:
        assert dates[0] <= m["date"] <= dates[-1]
        assert m["kind"] in {"data", "reported"}
        if m["kind"] == "reported":
            assert m["sources"] and all(s.startswith("https://") for s in m["sources"])
    by_label = {m["id"]: m for m in markers}
    assert by_label["issuance_step"]["date"] == "2025-10-30"
    first_buyback = cov["availability"]["buyback_near"]["first_date"]
    assert by_label["buyback_wallet_first_inflow"]["date"] == first_buyback
    assert {n["label"] for n in payload["not_drawn"]} >= {"nearcore 2.14 activation"}
    assert all(n["reason"] for n in payload["not_drawn"])


def test_coverage_series_carries_daily_volume(cov: dict) -> None:
    assert "volume_usd" in cov["series"][0]
    assert any(r["volume_usd"] for r in cov["series"])


def test_inflation_ramp_follows_hsp_029_with_its_grace_period(valuation: dict) -> None:
    assert config.INFLATION_GRACE_MONTHS == 3
    text = valuation["assumptions"]["inflation"]
    assert "HSP-029" in text and "90-day" in text


def test_summary_is_json_safe(summary: dict) -> None:
    json.dumps(summary, allow_nan=False)


def test_history_names_the_highest_30_day_coverage_and_when(cov: dict, summary: dict) -> None:
    best = summary["history"]["cr_float_30_max"]
    series = [(r["date"], r["cr_float_30"]) for r in cov["series"] if r["cr_float_30"] is not None]
    assert best["value"] == max(v for _, v in series)
    assert best["date"] == next(d for d, v in series if v == best["value"])
