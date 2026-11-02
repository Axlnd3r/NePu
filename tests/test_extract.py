"""Offline tests for the extraction layer: no network, no BigQuery."""

import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd
import pytest

from capture import config, snapshot
from capture import manifest as mf
from capture.extract import coingecko, defillama, fee_wallets, intents_explorer
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
from capture.extract.run import extract_bq_table

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


def test_explorer_throttle_cache_and_pagination(tmp_path: Path) -> None:
    fc = FakeClock()
    calls: list[dict] = []
    pages = [[_tx(i) for i in range(intents_explorer.PAGE_SIZE)], [_tx(9999)]]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        assert request.headers["authorization"] == "Bearer jwt"
        return httpx.Response(200, json=pages[len(calls) - 1])

    client = intents_explorer.ExplorerClient(
        "jwt",
        tmp_path,
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=fc.clock,
        sleep=fc.sleep,
    )
    rows = client.fetch_day(D(2026, 10, 30))
    assert len(rows) == intents_explorer.PAGE_SIZE + 1
    assert calls[1]["lastDepositAddress"] == f"addr{intents_explorer.PAGE_SIZE - 1}"
    assert fc.sleeps == [5.0]  # second request waited the full interval

    again = client.fetch_day(D(2026, 10, 30))  # served from the on-disk cache
    assert len(again) == len(rows) and client.requests_made == 2 and len(calls) == 2


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
