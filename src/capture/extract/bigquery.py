"""BigQuery extraction: dry-run first, then run under maximum_bytes_billed.

Every run is logged (bytes estimated and billed) to data/live/bytes_log.jsonl.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
from google.api_core import exceptions as gexc
from google.cloud import bigquery

from capture.extract.common import with_retries

DryRun = Callable[[date, date], int]
TRANSIENT = (
    gexc.ServiceUnavailable,
    gexc.InternalServerError,
    gexc.TooManyRequests,
    gexc.GatewayTimeout,
    ConnectionError,
)


class QueryTooLarge(RuntimeError):
    """A single day already exceeds the per-query byte limit."""


@dataclass(frozen=True)
class Chunk:
    start: date
    end: date
    dry_run_bytes: int


def plan_chunks(start: date, end: date, dry_run: DryRun, max_bytes: int) -> list[Chunk]:
    """Split [start, end] until every part's dry-run estimate fits under max_bytes."""
    est = dry_run(start, end)
    if est <= max_bytes:
        return [Chunk(start, end, est)]
    if start == end:
        raise QueryTooLarge(f"{start}: dry-run {est} bytes exceeds limit {max_bytes}")
    mid = start + timedelta(days=(end - start).days // 2)
    return plan_chunks(start, mid, dry_run, max_bytes) + plan_chunks(
        mid + timedelta(days=1), end, dry_run, max_bytes
    )


class BigQueryRunner:
    def __init__(
        self,
        project: str,
        max_bytes: int,
        log_path: Path,
        client: bigquery.Client | None = None,
    ) -> None:
        self.max_bytes = max_bytes
        self.log_path = log_path
        self.client = client or bigquery.Client(project=project)

    def _params(self, start: date, end: date, extra: list | None) -> list:
        return [
            bigquery.ScalarQueryParameter("start_date", "DATE", start),
            bigquery.ScalarQueryParameter("end_date", "DATE", end),
            *(extra or []),
        ]

    def dry_run_bytes(self, sql: str, start: date, end: date, extra: list | None = None) -> int:
        cfg = bigquery.QueryJobConfig(
            dry_run=True, use_query_cache=False, query_parameters=self._params(start, end, extra)
        )
        job = with_retries(lambda: self.client.query(sql, job_config=cfg), retry_on=TRANSIENT)
        return int(job.total_bytes_processed)

    def plan(self, sql: str, start: date, end: date, extra: list | None = None) -> list[Chunk]:
        return plan_chunks(
            start, end, lambda s, e: self.dry_run_bytes(sql, s, e, extra), self.max_bytes
        )

    def run_chunk(
        self, table: str, sql: str, chunk: Chunk, extra: list | None = None
    ) -> tuple[pd.DataFrame, int]:
        """Run one dry-run-approved chunk. Returns (rows, bytes billed)."""
        cfg = bigquery.QueryJobConfig(
            maximum_bytes_billed=self.max_bytes,
            query_parameters=self._params(chunk.start, chunk.end, extra),
        )

        def _run() -> bigquery.QueryJob:
            job = self.client.query(sql, job_config=cfg)
            job.result()
            return job

        job = with_retries(_run, retry_on=TRANSIENT)
        df = pd.DataFrame([dict(row) for row in job.result()])
        billed = int(job.total_bytes_billed or 0)
        self._log(table, chunk, billed, cache_hit=bool(job.cache_hit))
        return df, billed

    def _log(self, table: str, chunk: Chunk, billed: int, *, cache_hit: bool) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "table": table,
            "start": chunk.start.isoformat(),
            "end": chunk.end.isoformat(),
            "dry_run_bytes": chunk.dry_run_bytes,
            "billed_bytes": billed,
            "cache_hit": cache_hit,
        }
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


def wallets_param(wallets: tuple[str, ...]) -> list:
    return [bigquery.ArrayQueryParameter("wallets", "STRING", list(wallets))]
