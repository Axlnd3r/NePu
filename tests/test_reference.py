"""Reference checks added in F8: the HSP-029 vote, the official dashboard, the buyback wallet's
gross flows, the volume-invariant multiple, the definition table and the pre-registration."""

import json

import pandas as pd
import pytest

from capture import build, prereg
from capture.extract import governance, official
from capture.models import ledger, wallet_flows
from capture.models.valuation import breakeven_volume

YOCTO = 10**24


# ---------------------------------------------------------------- governance
def _record(status="Timelock", votes=(60, 0, 40), eligible=200, start_s=1_000):
    ns = 1_000_000_000
    return {
        "request": {"account_id": "vote.dao"},
        "block_height": 7,
        "proposal": {
            "id": 29,
            "title": "t",
            "link": "l",
            "status": status,
            "votes": [{"total_venear": str(v), "total_votes": 1} for v in votes],
            "total_votes": {"total_venear": str(sum(votes)), "total_votes": 3},
            "snapshot_and_state": {"total_venear": str(eligible)},
            "quorum_threshold_bps": 3500,
            "approval_threshold_bps": 6667,
            "voting_start_time_ns": str(start_s * ns),
            "voting_duration_ns": str(86_400 * ns),
            "timelock_duration_ns": str(2 * 86_400 * ns),
        },
    }


def test_the_vote_summary_is_derived_from_the_reply() -> None:
    s = governance.summarize(_record())
    assert s["status"] == "Timelock" and s["read_at_block"] == 7
    assert s["option_shares"] == [0.6, 0.0, 0.4] and s["top_option_share"] == 0.6
    assert s["turnout"] == 0.5 and s["approval_threshold"] == 0.6667
    assert s["voting_end_utc"] == "1970-01-02T00:16:40Z"
    assert s["timelock_end_utc"] == "1970-01-04T00:16:40Z"


def test_the_stored_hsp029_reply_is_a_closed_vote() -> None:
    raw = json.loads((build.REFERENCE / "hsp029_vote.json").read_text(encoding="utf-8"))
    s = governance.summarize(raw)
    assert s["proposal_id"] == 29 and s["contract"] == "vote.dao"
    assert 0 < s["turnout"] <= 1 and abs(sum(s["option_shares"]) - 1) < 1e-12


# ---------------------------------------------------------------- official dashboard
PAGE = (
    'x\\"absoluteRevEmissions\\":[{\\"date\\":\\"2026-01-01\\",\\"emissionsNear\\":100,'
    '\\"revenueNear\\":10,\\"offsetPct\\":0.1},{\\"date\\":\\"2026-01-03\\",'
    '\\"emissionsNear\\":300,\\"revenueNear\\":60,\\"offsetPct\\":0.2}]'
)


def test_the_official_series_is_parsed_and_read_on_or_before_a_day() -> None:
    rows = official.revenue_emissions(PAGE)
    assert [r["date"] for r in rows] == ["2026-01-01", "2026-01-03"]
    assert rows[1]["revenue_share"] == 0.2
    assert official.on(rows, "2026-01-02")["date"] == "2026-01-01"
    with pytest.raises(ValueError):
        official.on(rows, "2025-12-31")
    with pytest.raises(ValueError):
        official.revenue_emissions("no series here")


# ---------------------------------------------------------------- buyback wallet gross flows
def _activity(i, balance, who, ts_day):
    return {
        "event_index": str(i),
        "block_timestamp": str(int(pd.Timestamp(ts_day).value)),
        "involved_account_id": who,
        "absolute_nonstaked_amount": str(balance * YOCTO),
    }


def test_gross_flows_split_inflows_by_sender_and_list_outflows() -> None:
    acts = [
        _activity(1, 10, "intents.near", "2026-05-01 01:00"),
        _activity(2, 15, "intents.near", "2026-05-01 02:00"),
        _activity(3, 12, "someone.near", "2026-05-01 03:00"),  # an outflow hidden by the day's net
        _activity(4, 112, "1csfundsadmin.sputnik-dao.near", "2026-05-02"),
        _activity(5, 115, "tip.near", "2026-05-03"),
    ]
    changes = wallet_flows.activity_changes(acts, {"1csfundsadmin.sputnik-dao.near"})
    first, last = pd.Timestamp("2026-05-01"), pd.Timestamp("2026-05-03")
    flows = wallet_flows.gross_flows(changes, first, last)
    assert flows["inflow_near"] == {"intents": 15.0, "revenue_wallet": 100.0, "other": 3.0}
    assert flows["outflow_near"] == 3.0
    assert flows["outflows"] == [{"date": "2026-05-01", "to": "someone.near", "near": 3.0}]
    assert flows["net_near"] == 115.0 and flows["other_senders"] == 1


# ---------------------------------------------------------------- invariance and definitions
def test_the_multiple_is_the_same_whatever_the_volume_definition() -> None:
    out = ledger.volume_scale_invariance(
        100e6, 1.3e9, 4.0, 1_000.0, tau=0.0004, inflation=0.025, scales=(0.25, 1.0, 3.0)
    )
    multiples = {round(r["volume_multiple"], 12) for r in out["rows"]}
    assert len(multiples) == 1
    expected = breakeven_volume(0.025, 1.3e9, 4.0, 1_000.0, 0.0004) / 100e6
    assert abs(out["rows"][1]["volume_multiple"] - expected) < 1e-12
    assert out["rows"][0]["v_star_usd_per_day"] == pytest.approx(
        out["rows"][1]["v_star_usd_per_day"] * 0.25
    )


def test_the_definition_table_divides_by_issuance_over_the_same_days() -> None:
    days = pd.date_range("2026-01-01", "2026-04-30", freq="D")
    daily = pd.DataFrame(
        {
            "buyback_near": 1.0,
            "burnt_near": 0.5,
            "onchain_revenue_near": 2.0,
            "buyback_near_proxy": 3.0,
            "issuance_gross_near": 10.0,
            "near_usd": 2.0,
        },
        index=days,
    )
    rows = {r["id"]: r for r in ledger.definition_table(daily, days[-1])}
    assert rows["headline"]["value"] == pytest.approx(0.15)
    assert rows["all_wallets"]["value"] == pytest.approx(0.25)
    assert rows["defillama_proxy"]["value"] == pytest.approx(0.35)
    assert rows["all_wallets_ytd"]["value"] == pytest.approx(0.2)
    assert rows["all_wallets_ytd"]["days"] == len(days)
    assert rows["burn_only"]["value"] == pytest.approx(0.05)
    assert rows["window_90"]["days"] == 90


# ---------------------------------------------------------------- pre-registration
def _tests():
    return prereg.build_tests(
        registered_at="2026-11-09T08:00:00Z",
        inflow_per_day=1000.0,
        inflow_base=("2026-10-12", "2026-11-08"),
        cr_float_30=0.12,
        cr_date="2026-10-31",
        routing=0.65,
        routing_end="2026-10-30",
        tolerance=0.15,
        hsp029_status="Timelock",
        hsp029_block=1,
    )


def test_the_bands_come_from_the_values_measured_at_registration() -> None:
    t = {x["id"]: x for x in _tests()["tests"]}
    assert t["T1"]["pass_if"] == [2000.0, 8000.0]
    assert t["T2"]["pass_if"] == pytest.approx([0.06, 0.24])
    assert t["T3"]["pass_if"] == [0.325, 1.0]
    assert t["T4"]["pass_if"] == [0.0, 0.15]
    for test in t.values():
        assert "price" not in test["quantity"].lower() or "prices" in test["quantity"].lower()


def test_a_registration_is_written_once(tmp_path) -> None:
    written = prereg.write(_tests(), tmp_path)
    assert {p.name for p in written} == {"tests.json", "PREREG.md", "manifest.json"}
    with pytest.raises(FileExistsError):
        prereg.write(_tests(), tmp_path)


def test_scoring_waits_for_data_and_reports_a_miss_as_a_miss() -> None:
    t = {x["id"]: x for x in _tests()["tests"]}
    assert prereg.score_series(t["T2"], lambda d: None)["status"] == "pending"
    assert prereg.score_series(t["T2"], lambda d: 0.5)["status"] == "miss"
    assert prereg.score_series(t["T2"], lambda d: 0.1)["status"] == "pass"
    changes = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2026-11-11 00:00", "2026-11-12 00:00", "2026-11-14 01:00"]
            ),
            "kind": ["intents", "other", "intents"],
            "change_near": [3000.0, 5.0, 1.0],
        }
    )
    assert prereg.score_t1(t["T1"], changes) == {"status": "pass", "value": 3000.0}
    assert (
        prereg.score_t5(t["T5"], {"status": "Executed", "rejecter_id": None}, "2026-11-18")[
            "status"
        ]
        == "pass"
    )
    assert (
        prereg.score_t5(t["T5"], {"status": "Vetoed", "rejecter_id": None}, "2026-11-18")["status"]
        == "miss"
    )
    assert prereg.score_t5(t["T5"], None, None)["status"] == "pending"
