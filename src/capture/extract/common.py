"""Shared extraction helpers: retries, date coverage maths, atomic table writes."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from capture import manifest as mf
from capture.config import ROOT

DateRange = tuple[date, date]


def utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def with_retries[T](
    fn: Callable[[], T],
    *,
    tries: int = 5,
    base: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """Call fn, retrying on retry_on with exponential backoff (base, 2*base, 4*base, ...)."""
    for attempt in range(tries):
        try:
            return fn()
        except retry_on:
            if attempt == tries - 1:
                raise
            sleep(base * 2**attempt)
    raise AssertionError("unreachable")


def missing_ranges(covered: DateRange | None, start: date, end: date) -> list[DateRange]:
    """Ranges inside [start, end] not yet covered, in the order they must be fetched.

    Coverage is a single contiguous range, so the missing part is a tail after it (fetched
    ascending) and/or a head before it (fetched last, so coverage grows without gaps).
    """
    if start > end:
        return []
    if covered is None:
        return [(start, end)]
    c_start, c_end = covered
    out = []
    if end > c_end:
        out.append((max(start, c_end + timedelta(days=1)), end))
    if start < c_start:
        out.append((start, min(end, c_start - timedelta(days=1))))
    return out


def extend_coverage(covered: DateRange | None, chunk: DateRange) -> DateRange:
    """Union of covered and chunk; the chunk must touch or overlap the covered range."""
    if covered is None:
        return chunk
    c_start, c_end = covered
    if chunk[0] > c_end + timedelta(days=1) or chunk[1] < c_start - timedelta(days=1):
        raise ValueError(f"chunk {chunk} is not contiguous with covered range {covered}")
    return (min(c_start, chunk[0]), max(c_end, chunk[1]))


def merge_rows(existing: pd.DataFrame | None, new: pd.DataFrame, key: list[str]) -> pd.DataFrame:
    """New rows replace existing rows with the same key; result sorted by key."""
    if existing is None or existing.empty:
        merged = new
    elif new.empty:
        merged = existing
    else:
        merged = pd.concat([existing, new], ignore_index=True)
    return merged.drop_duplicates(subset=key, keep="last").sort_values(key).reset_index(drop=True)


def write_parquet_atomic(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def read_table(data_dir: Path, name: str) -> pd.DataFrame | None:
    path = data_dir / f"{name}.parquet"
    return pd.read_parquet(path) if path.exists() else None


def table_coverage(data_dir: Path, name: str) -> DateRange | None:
    """Requested date range recorded in the manifest for table `name`, if any."""
    if not (data_dir / mf.MANIFEST_NAME).exists():
        return None
    for entry in mf.read_manifest(data_dir):
        if entry.path == f"{name}.parquet" and entry.date_range:
            return (
                date.fromisoformat(entry.date_range[0]),
                date.fromisoformat(entry.date_range[1]),
            )
    return None


def store_table(
    data_dir: Path,
    name: str,
    df: pd.DataFrame,
    *,
    covered: DateRange,
    source: str,
    query_file: str | None,
    pulled_at_utc: str,
    root: Path = ROOT,
) -> mf.FileEntry:
    """Write df as data_dir/<name>.parquet and record it in the manifest.

    query_file is relative to root; its SHA-256 is stored so the data can be tied to the query.
    """
    path = data_dir / f"{name}.parquet"
    write_parquet_atomic(df, path)
    query_sha256 = None
    if query_file:
        query_sha256 = mf.sha256_file(root / query_file)
    entry = mf.make_entry(
        data_dir,
        path,
        source=source,
        pulled_at_utc=pulled_at_utc,
        query_file=query_file,
        date_range=(covered[0].isoformat(), covered[1].isoformat()),
        query_sha256=query_sha256,
    )
    mf.upsert_entries(data_dir, [entry])
    return entry
