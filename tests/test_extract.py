"""Offline tests for the extraction layer: no network, no BigQuery."""

import hashlib
import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd
import pytest

from capture import config, snapshot
from capture import manifest as mf
from capture.extract import coingecko, defillama, fee_wallets, intents_explorer, tokens
from capture.extract.bigquery import Chunk, QueryTooLarge, plan_chunks
from capture.extract.common import (
    extend_coverage,
    merge_rows,
    missing_ranges,
    read_table,
    store_table,
    table_coverage,
    with_retries,
)
from capture.extract.run import extract_bq_table, extract_explorer

D = date


def test_missing_ranges_cover_tail_and_head() -> None:
    assert missing_ranges(None, D(2026, 1, 1), D(2026, 1, 5)) == [(D(2026, 1, 1), D(2026, 1, 5))]
    covered = (D(2026, 1, 3), D(2026, 1, 5))
    assert missing_ranges(covered, D(2026, 1, 3), D(2026, 1, 5)) == []
    assert missing_ranges(covered, D(2026, 1, 1), D(2026, 1, 8)) == [
        (D(2026, 1, 6), D(2026, 1, 8)),
        (D(2026, 1, 1), D(2026, 1, 2)),
    ]
    assert missing_ranges(covered, D(2026, 1, 9), D(2026, 1, 4)) == []


def test_extend_coverage_requires_contiguity() -> None:
    covered = (D(2026, 1, 3), D(2026, 1, 5))
    assert extend_coverage(covered, (D(2026, 1, 6), D(2026, 1, 7))) == (
        D(2026, 1, 3),
        D(2026, 1, 7),
    )
    assert extend_coverage(covered, (D(2026, 1, 1), D(2026, 1, 2))) == (
        D(2026, 1, 1),
        D(2026, 1, 5),
    )
    with pytest.raises(ValueError):
        extend_coverage(covered, (D(2026, 1, 8), D(2026, 1, 9)))


def test_plan_chunks_splits_until_under_limit() -> None:
    per_day = 4
    dry = lambda s, e: ((e - s).days + 1) * per_day  # noqa: E731
    chunks = plan_chunks(D(2026, 1, 1), D(2026, 1, 10), dry, max_bytes=12)
    assert all(c.dry_run_bytes <= 12 for c in chunks)
    assert chunks[0].start == D(2026, 1, 1) and chunks[-1].end == D(2026, 1, 10)
    # contiguous, no overlap
    for a, b in zip(chunks, chunks[1:], strict=False):
        assert b.start == a.end + timedelta(days=1)
    assert sum((c.end - c.start).days + 1 for c in chunks) == 10


def test_plan_chunks_single_day_over_limit_raises() -> None:
    with pytest.raises(QueryTooLarge):
        plan_chunks(D(2026, 1, 1), D(2026, 1, 3), lambda s, e: 100, max_bytes=10)


def test_with_retries_backs_off_then_raises() -> None:
    sleeps: list[float] = []
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("boom")
        return "ok"

    assert with_retries(flaky, base=2.0, sleep=sleeps.append, retry_on=(ConnectionError,)) == "ok"
    assert sleeps == [2.0, 4.0]

    def always() -> str:
        raise ConnectionError("boom")

    sleeps.clear()
    with pytest.raises(ConnectionError):
        with_retries(always, tries=3, base=1.0, sleep=sleeps.append, retry_on=(ConnectionError,))
    assert sleeps == [1.0, 2.0]


def test_merge_rows_new_replaces_old() -> None:
    old = pd.DataFrame({"date": [D(2026, 1, 1), D(2026, 1, 2)], "v": [1, 2]})
    new = pd.DataFrame({"date": [D(2026, 1, 2), D(2026, 1, 3)], "v": [20, 3]})
    out = merge_rows(old, new, ["date"])
    assert out["v"].tolist() == [1, 20, 3]


def test_derive_inflows_net_change_and_gaps() -> None:
    raw = pd.DataFrame(
        {
            "date": [D(2026, 1, 1), D(2026, 1, 2), D(2026, 1, 4), D(2026, 1, 1)],
            "wallet": ["a", "a", "a", "b"],
            "token": ["NEAR"] * 4,
            "balance_end": [10.0, 12.5, 12.0, 5.0],
        }
    )
    out = fee_wallets.derive_inflows(raw)
    a = out[out["wallet"] == "a"].reset_index(drop=True)
    assert pd.isna(a.loc[0, "amount"]) and pd.isna(a.loc[0, "amount_raw"])  # first day unknown
    assert a.loc[1, "amount"] == pytest.approx(2.5)
    assert a.loc[1, "amount_raw"] == str(round(2.5 * 10**24))
    assert a.loc[2, "amount"] == pytest.approx(-0.5) and a.loc[2, "days_since_prev"] == 2
    assert set(out["decimals"]) == {24}
    assert out[out["wallet"] == "b"]["amount"].isna().all()


def test_coingecko_plan_and_daily() -> None:
    reqs = coingecko.plan_requests(D(2025, 5, 10), D(2026, 11, 1))
    assert len(reqs) == 2 and reqs[0][0] == D(2025, 5, 10) and reqs[-1][1] == D(2026, 11, 1)
    assert all((hi - lo).days + 1 <= coingecko.MAX_SPAN_DAYS for lo, hi in reqs)
    assert reqs[1][0] == reqs[0][1] + timedelta(days=1)
    assert coingecko.plan_requests(D(2026, 10, 1), D(2026, 10, 5)) == [
        (D(2026, 10, 1), D(2026, 10, 5))
    ]
    ms = lambda y, m, d, h: int(datetime(y, m, d, h, tzinfo=UTC).timestamp() * 1000)  # noqa: E731
    daily = coingecko.to_daily(
        [[ms(2026, 10, 2, 5), 7.0], [ms(2026, 10, 2, 0), 5.0], [ms(2026, 10, 3, 0), 6.0]]
    )
    assert daily == {D(2026, 10, 2): 5.0, D(2026, 10, 3): 6.0}


def test_coingecko_fetch_with_mock_transport() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        lo = int(request.url.params["from"])
        points = [[(lo + i * 86400) * 1000, 4.0 + i] for i in range(0, 120)]
        return httpx.Response(200, json={"prices": points})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    df = coingecko.fetch_near_usd(
        D(2026, 1, 10), D(2026, 1, 12), client=client, sleep=lambda s: None
    )
    assert df["date"].tolist() == [D(2026, 1, 10), D(2026, 1, 11), D(2026, 1, 12)]
    assert df["near_usd"].notna().all()


def test_coingecko_missing_prices_raises() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"error": "x"}))
    )
    with pytest.raises(RuntimeError, match="without prices"):
        coingecko.fetch_near_usd(
            D(2026, 1, 10), D(2026, 1, 12), client=client, sleep=lambda s: None
        )


def _chart(values: dict[date, float]) -> dict:
    ts = lambda d: int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp())  # noqa: E731
    return {"totalDataChart": [[ts(d), v] for d, v in values.items()]}


def test_defillama_build_table_drops_non_final_days_and_counts_revisions() -> None:
    days = [D(2026, 10, 28), D(2026, 10, 29), D(2026, 10, 30), D(2026, 10, 31)]
    series = {
        col: defillama.parse_chart(_chart({d: float(i + 1) for i, d in enumerate(days)}))
        for col in defillama.SERIES
    }
    series["volume_usd"].pop(D(2026, 10, 28))  # volume missing on the first day
    table = defillama.build_table(series, last_final=D(2026, 10, 30))
    assert table["date"].tolist() == days[:3]
    assert pd.isna(table.loc[0, "volume_usd"]) and table.loc[0, "fees_usd"] == 1.0
    revised = table.copy()
    revised.loc[1, "fees_usd"] = 99.0
    assert defillama.count_revisions(table, revised) == 1
    assert defillama.count_revisions(None, revised) == 0


def test_defillama_fetch_with_mock_transport() -> None:
    values = {
        D(2026, 10, 28): 1.0,
        D(2026, 10, 29): 2.0,
        D(2026, 10, 30): 3.0,
        D(2026, 10, 31): 4.0,
    }
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=_chart(values)))
    )
    df = defillama.fetch(lag_days=3, today=D(2026, 11, 2), client=client)
    assert df["date"].max() == D(2026, 10, 30)  # last_final = today - 3


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _tx(i: int, asset_in: str = "nep141:wrap.near", fee_to: str | None = "near.near") -> dict:
    return {
        "depositAddress": f"addr{i}",
        "depositMemo": None,
        "originAsset": asset_in,
        "destinationAsset": "nep141:eth-0xabc.omft.near",
        "amountInUsd": "10.5",
        "appFees": [{"recipient": fee_to, "fee": 50}] if fee_to else [],
    }


def _day_txs(day: date, count: int, tie_at: int | None = None) -> list[dict]:
    """`count` transactions of `day`, newest first, 100 s apart; row tie_at shares its
    predecessor's second (older milliseconds), as happens at a page boundary."""
    end = int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp()) + 86400
    txs = []
    for i in range(count):
        sec = end - 1 - i * 100
        ms = 900
        if tie_at is not None and i == tie_at:
            sec, ms = txs[-1]["createdAtTimestamp"], 100
        created = datetime.fromtimestamp(sec, UTC).strftime("%Y-%m-%dT%H:%M:%S") + f".{ms:03d}Z"
        txs.append({**_tx(i), "createdAt": created, "createdAtTimestamp": sec})
    return txs


def _fake_explorer(txs: list[dict], calls: list[dict]):
    """Emulates the Explorer API filter: start < createdAtTimestamp < end, newest first. Like the
    real API on 2026-10-10 it ignores lastDepositAddress (the client must not rely on it)."""

    def handler(request: httpx.Request) -> httpx.Response:
        q = dict(request.url.params)
        calls.append(q)
        lo, hi, n = (
            int(q["startTimestampUnix"]),
            int(q["endTimestampUnix"]),
            int(q["numberOfTransactions"]),
        )
        rows = [t for t in txs if lo < t["createdAtTimestamp"] < hi]
        rows.sort(key=lambda t: t["createdAt"], reverse=True)
        return httpx.Response(200, json=rows[:n])

    return handler


def _client(tmp_path: Path, handler, fc: "FakeClock") -> intents_explorer.ExplorerClient:
    return intents_explorer.ExplorerClient(
        "jwt",
        tmp_path,
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=fc.clock,
        sleep=fc.sleep,
    )


def test_explorer_pages_back_in_time_without_cursor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(intents_explorer, "PAGE_SIZE", 100)
    day = D(2026, 10, 30)
    txs = _day_txs(day, 250, tie_at=100)  # rows 99 and 100 share a second across the boundary
    calls: list[dict] = []
    fc = FakeClock()
    client = _client(tmp_path, _fake_explorer(txs, calls), fc)

    rows = client.fetch_day(day)
    ids = [(r["depositAddress"], r["createdAt"]) for r in rows]
    assert len(rows) == 250 and len(set(ids)) == 250  # complete, no duplicates
    assert [r["createdAt"] for r in rows] == sorted((r["createdAt"] for r in rows), reverse=True)
    assert all("lastDepositAddress" not in c for c in calls)
    assert len(calls) == 3 and client.requests_made == 3
    assert fc.sleeps == [5.0, 5.0]  # 1 request per 5 s

    again = client.fetch_day(day)  # served from the on-disk cache
    assert len(again) == 250 and client.requests_made == 3 and len(calls) == 3


def test_explorer_stuck_pagination_raises_instead_of_looping(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(intents_explorer, "PAGE_SIZE", 100)
    day = D(2026, 10, 30)
    same_second = int(datetime(2026, 10, 30, 12, tzinfo=UTC).timestamp())
    txs = []
    for i in range(150):  # more rows in one second than a page holds
        txs.append(
            {
                **_tx(i),
                "createdAt": f"2026-10-30T12:00:00.{i:03d}Z",
                "createdAtTimestamp": same_second,
            }
        )
    client = _client(tmp_path, _fake_explorer(txs, []), FakeClock())
    with pytest.raises(RuntimeError, match="stuck"):
        client.fetch_day(day)


def test_explorer_stops_at_page_limit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(intents_explorer, "PAGE_SIZE", 2)
    monkeypatch.setattr(intents_explorer, "MAX_PAGES_PER_DAY", 3)
    day = D(2026, 10, 30)
    client = _client(tmp_path, _fake_explorer(_day_txs(day, 50), []), FakeClock())
    with pytest.raises(RuntimeError, match="more than 3 pages"):
        client.fetch_day(day)


def test_explorer_429_waits_and_retries(tmp_path: Path) -> None:
    fc = FakeClock()
    answers = iter([429, 429, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        code = next(answers)
        return httpx.Response(code, json=[] if code == 200 else {"error": "slow down"})

    client = intents_explorer.ExplorerClient(
        "jwt",
        tmp_path,
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=fc.clock,
        sleep=fc.sleep,
    )
    assert client.get({"a": 1}) == []
    assert fc.sleeps == [5.0, 5.0] and client.requests_made == 3


def test_explorer_aggregate_day() -> None:
    txs = [_tx(1), _tx(2), _tx(3, fee_to=None)]
    rows = intents_explorer.aggregate_day(D(2026, 10, 30), txs)
    by_aff = {r["affiliate"]: r for r in rows}
    assert by_aff["near.near"]["tx_count"] == 2 and by_aff["near.near"][
        "volume_usd"
    ] == pytest.approx(21.0)
    assert by_aff[""]["tx_count"] == 1
    # fee is in basis points of amountIn: 2 txs x 10.5 USD x 50 bps
    assert by_aff["near.near"]["fee_usd"] == pytest.approx(21.0 * 50 / 10_000)
    assert by_aff[""]["fee_usd"] == 0.0


@pytest.mark.parametrize(
    ("asset", "chain"),
    [
        ("nep141:eth-0xabc.omft.near", "eth"),
        ("nep141:arb-0xaf88d065e77c8cc2239327c5edb3a432268e5831.omft.near", "arb"),
        ("nep141:sol.omft.near", "sol"),
        ("nep141:xrp.omft.near", "xrp"),
        ("nep141:wrap.near", "near"),
        ("nep141:usdt.tether-token.near", "near"),
        ("nep245:v2_1.omni.hot.tg:56_2CMMyVTGZkeyNZTSvS5sarzfir6g", "hot:56"),
        ("nep245:v2_1.omni.hot.tg:1117_", "hot:1117"),
        ("nep141:17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1", "near"),
        ("1cs_v1:btc:native:coin", "btc"),
        ("1cs_v1:starknet:erc20:0x05ce53b9b68fb8e9ecab9283a96d97948914733fd6ed", "starknet"),
        ("1cs_v1:near:nep141:zec.omft.near", "near"),
        ("weird", "unknown"),
    ],
)
def test_chain_of_patterns_seen_in_real_data(asset: str, chain: str) -> None:
    assert intents_explorer.chain_of(asset) == chain


def test_store_table_records_manifest_and_coverage(tmp_path: Path) -> None:
    (tmp_path / "sql").mkdir()
    (tmp_path / "sql" / "t.sql").write_text("SELECT 1", encoding="utf-8")
    data = tmp_path / "data" / "live"
    df = pd.DataFrame({"date": [D(2026, 1, 1), D(2026, 1, 2)], "v": [1, 2]})
    store_table(
        data, "t", df, covered=(D(2026, 1, 1), D(2026, 1, 2)), source="test",
        query_file="sql/t.sql", pulled_at_utc="2026-11-02T00:00:00Z", root=tmp_path,
    )  # fmt: skip
    [entry] = mf.read_manifest(data)
    assert entry.rows == 2 and entry.date_range == ("2026-01-01", "2026-01-02")
    assert entry.query_sha256 == mf.sha256_file(tmp_path / "sql" / "t.sql")
    assert table_coverage(data, "t") == (D(2026, 1, 1), D(2026, 1, 2))
    assert mf.verify_manifest(data) == []
    assert read_table(data, "nope") is None and table_coverage(data, "nope") is None


class FakeRunner:
    """Stands in for BigQueryRunner: 2-day chunks, 1000 billed bytes each, counts queries."""

    def __init__(self) -> None:
        self.runs: list[Chunk] = []

    def plan(self, sql: str, start: date, end: date, extra=None) -> list[Chunk]:
        out, cur = [], start
        while cur <= end:
            stop = min(end, cur + timedelta(days=1))
            out.append(Chunk(cur, stop, 1000))
            cur = stop + timedelta(days=1)
        return out

    def run_chunk(self, table: str, sql: str, chunk: Chunk, extra=None):
        self.runs.append(chunk)
        days = [chunk.start + timedelta(days=i) for i in range((chunk.end - chunk.start).days + 1)]
        return pd.DataFrame({"date": days, "intents_calls": [len(self.runs)] * len(days)}), 1000


def test_extract_bq_table_is_incremental(tmp_path: Path) -> None:
    spec = config.BQ_TABLES["intents_onchain_daily"]
    runner = FakeRunner()
    today = D(2026, 5, 6)  # last complete day = 2026-05-05
    first = extract_bq_table(spec, runner, tmp_path, start=D(2026, 5, 1), today=today)
    assert first.status == "ok" and first.rows_total == 5 and first.billed_bytes == 3000
    assert first.covered == (D(2026, 5, 1), D(2026, 5, 5))

    again = extract_bq_table(spec, runner, tmp_path, start=D(2026, 5, 1), today=today)
    assert again.status == "up-to-date" and again.billed_bytes == 0 and len(runner.runs) == 3

    nxt = extract_bq_table(spec, runner, tmp_path, start=D(2026, 5, 1), today=D(2026, 5, 7))
    assert nxt.rows_added == 1 and nxt.covered == (D(2026, 5, 1), D(2026, 5, 6))

    back = extract_bq_table(spec, runner, tmp_path, start=D(2026, 4, 29), today=D(2026, 5, 7))
    assert back.covered == (D(2026, 4, 29), D(2026, 5, 6)) and back.rows_total == 8
    assert mf.verify_manifest(tmp_path) == []


def test_extract_bq_table_dry_run_only_pulls_nothing(tmp_path: Path) -> None:
    spec = config.BQ_TABLES["network_daily"]
    runner = FakeRunner()
    res = extract_bq_table(
        spec, runner, tmp_path, start=D(2026, 5, 1), dry_run_only=True, today=D(2026, 5, 6)
    )
    assert res.status == "dry-run" and res.estimated_bytes == 3000 and runner.runs == []
    assert not (tmp_path / "network_daily.parquet").exists()


def _write_live(live: Path, covered_end: date) -> None:
    df = pd.DataFrame(
        {"date": [D(2026, 5, 1) + timedelta(days=i) for i in range(6)], "v": range(6)}
    )
    store_table(
        live, "t", df, covered=(D(2026, 5, 1), covered_end), source="test", query_file=None,
        pulled_at_utc="2026-05-07T00:00:00Z",
    )  # fmt: skip


def test_snapshot_freeze_filters_rows_and_rewrites_manifest(tmp_path: Path) -> None:
    live, snap = tmp_path / "live", tmp_path / "snap"
    _write_live(live, D(2026, 5, 6))
    snap.mkdir()
    (snap / "stale.parquet").write_bytes(b"x")
    entries = snapshot.freeze(D(2026, 5, 4), live, snap, today=D(2026, 5, 7))
    [entry] = entries
    assert entry.rows == 4 and entry.date_range == ("2026-05-01", "2026-05-04")
    assert not (snap / "stale.parquet").exists()
    assert mf.verify_manifest(snap) == []


def test_snapshot_refuses_incomplete_day_and_bad_live_manifest(tmp_path: Path) -> None:
    live, snap = tmp_path / "live", tmp_path / "snap"
    _write_live(live, D(2026, 5, 6))
    with pytest.raises(ValueError, match="complete UTC day"):
        snapshot.freeze(D(2026, 5, 7), live, snap, today=D(2026, 5, 7))
    (live / "t.parquet").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="does not match"):
        snapshot.freeze(D(2026, 5, 4), live, snap, today=D(2026, 5, 7))


@pytest.mark.parametrize("name", sorted(config.BQ_TABLES))
def test_sql_files_follow_the_rules(name: str) -> None:
    sql = config.BQ_TABLES[name].sql_path.read_text(encoding="utf-8")
    code = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    assert not re.search(r"select\s+\*", code, re.IGNORECASE), "never SELECT * (rule 2)"
    date_col = "epoch_date" if name == "fee_wallet_inflows_daily" else "block_date"
    assert f"{date_col} BETWEEN @start_date AND @end_date" in code


def test_committed_snapshot_queries_match_sql_files() -> None:
    """A snapshot must correspond to the SQL in the repo (CLAUDE.md rule 3)."""
    for entry in mf.read_manifest(config.DATA_SNAPSHOT):
        if entry.query_file:
            current = mf.sha256_file(config.ROOT / entry.query_file)
            assert entry.query_sha256 == current, f"{entry.query_file} changed since snapshot"


def test_bytes_log_is_valid_jsonl_when_present() -> None:
    log = config.DATA_LIVE / "bytes_log.jsonl"
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            assert {"table", "dry_run_bytes", "billed_bytes"} <= json.loads(line).keys()


def _ref_tx(
    i: int, referral: str | None, recipients: list[tuple[str, int]], usd: str = "100"
) -> dict:
    return {
        **_tx(i),
        "referral": referral,
        "amountInUsd": usd,
        "appFees": [{"recipient": r, "fee": bps} for r, bps in recipients],
    }


def test_channel_and_recipient_aggregation() -> None:
    day = D(2026, 10, 30)
    txs = [
        _ref_tx(1, "swapkit", [("a.near", 50), ("b.near", 20)]),
        _ref_tx(2, "swapkit", [("a.near", 50)]),
        _ref_tx(3, None, []),
        _ref_tx(4, None, [("near.wallet", 10)], usd="200"),
    ]
    channels = {r["referral"]: r for r in intents_explorer.aggregate_channels(day, txs)}
    assert set(channels) == {"swapkit", "(none)"}
    assert channels["swapkit"]["volume_usd"] == pytest.approx(200.0)
    assert channels["swapkit"]["fee_usd"] == pytest.approx(100 * 70 / 1e4 + 100 * 50 / 1e4)
    assert channels["(none)"]["tx_count"] == 2 and channels["(none)"][
        "volume_usd"
    ] == pytest.approx(300.0)
    # channel volumes add up to the total of the day
    assert sum(r["volume_usd"] for r in channels.values()) == pytest.approx(500.0)

    rec = {
        (r["referral"], r["recipient"]): r for r in intents_explorer.aggregate_recipients(day, txs)
    }
    assert rec[("swapkit", "a.near")]["volume_usd"] == pytest.approx(200.0)
    assert rec[("swapkit", "b.near")]["fee_usd"] == pytest.approx(100 * 20 / 1e4)
    assert (
        rec[("(none)", "(none)")]["tx_count"] == 1 and rec[("(none)", "(none)")]["fee_usd"] == 0.0
    )
    # volume is not additive across recipients: tx 1 sits in both a.near and b.near
    assert sum(r["volume_usd"] for r in rec.values()) > 500.0
    # fee is additive: it equals the channel total
    assert sum(r["fee_usd"] for r in rec.values()) == pytest.approx(
        sum(r["fee_usd"] for r in channels.values())
    )


def test_cache_keeps_only_the_fields_the_model_uses(tmp_path: Path) -> None:
    full = {
        **_tx(1),
        "senders": ["x"] * 50,
        "nearTxHashes": ["h"] * 50,
        "refundReason": None,
        "status": "SUCCESS",
    }
    slim = intents_explorer._slim([full])[0]
    assert set(slim) <= set(intents_explorer.SLIM_FIELDS) and "senders" not in slim
    assert len(json.dumps(slim)) < len(json.dumps(full)) / 2


class DayClient:
    """Stands in for ExplorerClient: 10 deterministic transactions a day; records the days asked."""

    def __init__(self) -> None:
        self.days: list[date] = []

    def fetch_day(self, day: date) -> list[dict]:
        self.days.append(day)
        return [
            _ref_tx(
                i,
                "swapkit" if i % 2 else None,
                [("a.near", 50)] if i % 2 else [],
                usd=str(10 + day.day),
            )
            | {
                "createdAt": f"{day.isoformat()}T00:00:{i:02d}.000Z",
                "createdAtTimestamp": 1_000 + i,
            }
            for i in range(10)
        ]


def test_extract_explorer_group_is_incremental_resumable_and_backfills(tmp_path: Path) -> None:
    client = DayClient()
    today = D(2026, 10, 11)  # last complete day = 2026-10-10
    first = extract_explorer(
        tmp_path, {}, start=D(2026, 10, 5), today=today, client=client, chunk_days=3
    )
    assert first.status == "ok" and first.covered == (D(2026, 10, 5), D(2026, 10, 10))
    assert len(client.days) == 6
    for name in config.EXPLORER_TABLES:  # all three written together, with the same coverage
        assert table_coverage(tmp_path, name) == (D(2026, 10, 5), D(2026, 10, 10))
    daily = read_table(tmp_path, "explorer_1click_daily")
    channels = read_table(tmp_path, "explorer_channels_daily")
    assert daily["tx_count"].sum() == 60 and channels["tx_count"].sum() == 60
    assert daily["volume_usd"].sum() == pytest.approx(channels["volume_usd"].sum())

    again = extract_explorer(
        tmp_path, {}, start=D(2026, 10, 5), today=today, client=client, chunk_days=3
    )
    assert again.status == "up-to-date" and len(client.days) == 6  # nothing fetched twice

    back = extract_explorer(
        tmp_path, {}, start=D(2026, 10, 1), today=today, client=client, chunk_days=3
    )
    assert back.covered == (D(2026, 10, 1), D(2026, 10, 10)) and len(client.days) == 10
    # head range 10-01..10-04 = [10-01..10-03] + [10-04]; the newest chunk runs first
    assert client.days[6:8] == [D(2026, 10, 4), D(2026, 10, 1)]
    assert read_table(tmp_path, "explorer_1click_daily")["tx_count"].sum() == 100
    assert mf.verify_manifest(tmp_path) == []


def test_extract_explorer_without_jwt_is_skipped(tmp_path: Path) -> None:
    assert extract_explorer(tmp_path, {}).status == "skipped"


def test_tokens_table_keeps_only_identifiers() -> None:
    payload = [
        {
            "assetId": "nep141:zec.omft.near",
            "symbol": "ZEC",
            "blockchain": "zec",
            "decimals": 8,
            "price": 1.0,
        },
        {
            "assetId": "nep141:wrap.near",
            "symbol": "wNEAR",
            "blockchain": "near",
            "decimals": 24,
            "price": 4.0,
        },
        {
            "assetId": "nep141:wrap.near",
            "symbol": "wNEAR",
            "blockchain": "near",
            "decimals": 24,
            "price": 4.1,
        },
    ]
    frame = tokens.to_frame(payload)
    assert list(frame.columns) == ["asset_id", "symbol", "blockchain", "decimals"]
    assert frame["asset_id"].tolist() == [
        "nep141:wrap.near",
        "nep141:zec.omft.near",
    ]  # sorted, deduplicated


def test_snapshot_copies_tables_without_a_date_column(tmp_path: Path) -> None:
    live, snap = tmp_path / "live", tmp_path / "snap"
    _write_live(live, D(2026, 5, 6))
    store_table(
        live, "token_assets", pd.DataFrame({"asset_id": ["a", "b"], "symbol": ["X", "Y"]}),
        covered=None, source="test", query_file=None, pulled_at_utc="2026-05-07T00:00:00Z",
    )  # fmt: skip
    entries = {e.path: e for e in snapshot.freeze(D(2026, 5, 4), live, snap, today=D(2026, 5, 7))}
    assert (
        entries["token_assets.parquet"].rows == 2
        and entries["token_assets.parquet"].date_range is None
    )
    assert entries["t.parquet"].rows == 4
    assert mf.verify_manifest(snap) == []


def test_explorer_survives_a_cache_page_cut_short_by_a_stop(tmp_path: Path) -> None:
    calls: list[dict] = []
    client = _client(tmp_path, _fake_explorer(_day_txs(D(2026, 10, 30), 5), calls), FakeClock())
    params = {"numberOfTransactions": 1000, "startTimestampUnix": 0, "endTimestampUnix": 2**31}
    key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
    (tmp_path / f"{key}.json").write_text('[{"depositAddress": "tru', encoding="utf-8")  # cut short

    page = client.get(params)
    assert len(calls) == 1 and len(page) == 5  # the broken file was treated as a miss
    assert json.loads((tmp_path / f"{key}.json").read_text(encoding="utf-8")) == page  # repaired
    assert not list(tmp_path.glob("*.tmp"))  # no temporary file left behind
    assert client.get(params) == page and len(calls) == 1  # now served from the cache


def test_explorer_retries_after_a_timeout(tmp_path: Path) -> None:
    txs = _day_txs(D(2026, 10, 30), 5)
    calls: list[dict] = []
    ok = _fake_explorer(txs, calls)
    attempts = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise httpx.ReadTimeout("The read operation timed out", request=request)
        return ok(request)

    client = _client(tmp_path, flaky, FakeClock())
    assert len(client.fetch_day(D(2026, 10, 30))) == 5
    assert attempts["n"] == 2  # one timeout, then the retry succeeded
