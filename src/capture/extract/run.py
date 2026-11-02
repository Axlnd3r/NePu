"""Orchestration for `capture extract`: incremental by date, one parquet file per table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import httpx

from capture import config
from capture.config import BQ_TABLES, BqTable
from capture.extract import coingecko, defillama, fee_wallets, intents_explorer
from capture.extract.bigquery import BigQueryRunner, wallets_param
from capture.extract.common import (
    DateRange,
    extend_coverage,
    merge_rows,
    missing_ranges,
    read_table,
    store_table,
    table_coverage,
    utc_now_iso,
)

EXPLORER_DEFAULT_DAYS = 30
RAW_WALLET_COLUMNS = ["date", "wallet", "token", "balance_end"]


@dataclass
class TableResult:
    name: str
    status: str  # ok | up-to-date | dry-run | skipped
    rows_total: int = 0
    rows_added: int = 0
    covered: DateRange | None = None
    billed_bytes: int = 0
    estimated_bytes: int = 0
    note: str = ""


def _existing_rows(data_dir: Path, name: str) -> int:
    df = read_table(data_dir, name)
    return 0 if df is None else len(df)


def extract_bq_table(
    spec: BqTable,
    runner: BigQueryRunner,
    data_dir: Path,
    *,
    start: date | None = None,
    end: date | None = None,
    dry_run_only: bool = False,
    today: date | None = None,
) -> TableResult:
    sql = spec.sql_path.read_text(encoding="utf-8")
    extra = wallets_param(config.FEE_WALLETS) if spec.name == "fee_wallet_inflows_daily" else None
    cap = config.last_complete_day(today) - timedelta(days=spec.lag_days)
    want_start, want_end = start or spec.start, min(end or cap, cap)
    covered = table_coverage(data_dir, spec.name)
    ranges = missing_ranges(covered, want_start, want_end)
    result = TableResult(spec.name, "up-to-date", rows_total=_existing_rows(data_dir, spec.name))
    result.covered = covered
    for lo, hi in ranges:
        chunks = runner.plan(sql, lo, hi, extra)
        if dry_run_only:
            result.status = "dry-run"
            result.estimated_bytes += sum(c.dry_run_bytes for c in chunks)
            continue
        if covered is not None and hi < covered[0]:
            chunks.reverse()  # backfill: grow coverage backwards without gaps
        for chunk in chunks:
            df, billed = runner.run_chunk(spec.name, sql, chunk, extra)
            existing = read_table(data_dir, spec.name)
            if spec.name == "fee_wallet_inflows_daily":
                raw = None if existing is None else existing[RAW_WALLET_COLUMNS]
                merged = merge_rows(raw, df, list(spec.key))
                merged = fee_wallets.derive_inflows(merged) if not merged.empty else merged
            else:
                merged = merge_rows(existing, df, list(spec.key))
            if merged.empty:
                raise RuntimeError(f"{spec.name}: no rows for {chunk.start}..{chunk.end}")
            covered = extend_coverage(covered, (chunk.start, chunk.end))
            store_table(
                data_dir,
                spec.name,
                merged,
                covered=covered,
                source=f"bigquery:{config.DATASET}",
                query_file=spec.query_file,
                pulled_at_utc=utc_now_iso(),
            )
            result.status = "ok"
            result.rows_added += len(df)
            result.rows_total = len(merged)
            result.billed_bytes += billed
            result.estimated_bytes += chunk.dry_run_bytes
            result.covered = covered
    return result


def extract_defillama(
    data_dir: Path, *, today: date | None = None, client: httpx.Client | None = None
) -> TableResult:
    name = "defillama_intents_daily"
    old = read_table(data_dir, name)
    new = defillama.fetch(config.DEFILLAMA_LAG_DAYS, today, client)
    revisions = defillama.count_revisions(old, new)
    covered = (new["date"].min(), new["date"].max())
    store_table(
        data_dir,
        name,
        new,
        covered=covered,
        source=defillama.sources(),
        query_file=None,
        pulled_at_utc=utc_now_iso(),
    )
    added = len(new) - (0 if old is None else len(old))
    note = f"{revisions} previously stored values revised"
    return TableResult(name, "ok", len(new), max(added, 0), covered, note=note)


def extract_price(
    data_dir: Path,
    settings: dict[str, str],
    *,
    start: date | None = None,
    end: date | None = None,
    today: date | None = None,
    client: httpx.Client | None = None,
) -> TableResult:
    name = "price_daily"
    want_end = end or config.last_complete_day(today)
    oldest_allowed = want_end - timedelta(days=config.PRICE_PUBLIC_WINDOW_DAYS - 1)
    want_start = start or max(config.PRICE_START, oldest_allowed)
    covered = table_coverage(data_dir, name)
    result = TableResult(name, "up-to-date", _existing_rows(data_dir, name), covered=covered)
    for lo, hi in missing_ranges(covered, want_start, want_end):
        df = coingecko.fetch_near_usd(lo, hi, settings.get("COINGECKO_API_KEY"), client)
        if df.empty:
            raise RuntimeError(f"{name}: CoinGecko returned no prices for {lo}..{hi}")
        merged = merge_rows(read_table(data_dir, name), df, ["date"])
        covered = extend_coverage(covered, (lo, hi))
        store_table(
            data_dir,
            name,
            merged,
            covered=covered,
            source=coingecko.URL,
            query_file=None,
            pulled_at_utc=utc_now_iso(),
        )
        result.status, result.rows_added = "ok", result.rows_added + len(df)
        result.rows_total, result.covered = len(merged), covered
    return result


def extract_explorer(
    data_dir: Path,
    settings: dict[str, str],
    *,
    start: date | None = None,
    end: date | None = None,
    today: date | None = None,
    client: intents_explorer.ExplorerClient | None = None,
) -> TableResult:
    name = "explorer_1click_daily"
    jwt = settings.get("INTENTS_EXPLORER_JWT")
    if client is None and not jwt:
        return TableResult(name, "skipped", note="INTENTS_EXPLORER_JWT not set")
    client = client or intents_explorer.ExplorerClient(jwt or "", data_dir / "_cache" / "explorer")
    want_end = end or config.last_complete_day(today)
    want_start = start or want_end - timedelta(days=EXPLORER_DEFAULT_DAYS - 1)
    covered = table_coverage(data_dir, name)
    result = TableResult(name, "up-to-date", _existing_rows(data_dir, name), covered=covered)
    key = ["date", "affiliate", "asset_in", "asset_out", "chain"]
    for lo, hi in missing_ranges(covered, want_start, want_end):
        days = [lo + timedelta(days=i) for i in range((hi - lo).days + 1)]
        df = intents_explorer.fetch_days(client, days)
        existing = read_table(data_dir, name)
        out = merge_rows(existing, df, key) if not df.empty else existing
        covered = extend_coverage(covered, (lo, hi))
        if out is None or out.empty:
            continue
        store_table(
            data_dir,
            name,
            out,
            covered=covered,
            source=intents_explorer.URL,
            query_file=None,
            pulled_at_utc=utc_now_iso(),
        )
        result.status, result.rows_added = "ok", result.rows_added + len(df)
        result.rows_total, result.covered = len(out), covered
    return result


def run_extract(
    tables: list[str],
    settings: dict[str, str],
    data_dir: Path,
    *,
    start: date | None = None,
    end: date | None = None,
    dry_run_only: bool = False,
) -> list[TableResult]:
    results: list[TableResult] = []
    bq_names = [t for t in tables if t in BQ_TABLES]
    if bq_names:
        try:
            project, max_bytes = settings["GOOGLE_CLOUD_PROJECT"], int(settings["BQ_MAX_BYTES"])
        except KeyError as exc:
            raise RuntimeError(f"{exc.args[0]} is not set in .env") from exc
        runner = BigQueryRunner(project, max_bytes, data_dir / "bytes_log.jsonl")
        for name in bq_names:
            results.append(
                extract_bq_table(
                    BQ_TABLES[name],
                    runner,
                    data_dir,
                    start=start,
                    end=end,
                    dry_run_only=dry_run_only,
                )
            )
    if dry_run_only:
        return results
    if "defillama_intents_daily" in tables:
        results.append(extract_defillama(data_dir))
    if "price_daily" in tables:
        results.append(extract_price(data_dir, settings, start=start, end=end))
    if "explorer_1click_daily" in tables:
        results.append(extract_explorer(data_dir, settings, start=start, end=end))
    return results
