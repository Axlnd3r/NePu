"""Freeze data/live into data/snapshot with a new manifest (CLAUDE.md rule 3)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from capture import manifest as mf
from capture.config import DATA_LIVE, DATA_SNAPSHOT, last_complete_day
from capture.extract.common import write_parquet_atomic


def freeze(
    freeze_date: date,
    live_dir: Path = DATA_LIVE,
    snapshot_dir: Path = DATA_SNAPSHOT,
    today: date | None = None,
) -> list[mf.FileEntry]:
    """Copy every live table, keeping rows with date <= freeze_date, and rewrite the manifest.

    Refuses a freeze date that is not a complete UTC day, and a live directory whose manifest
    does not match its files. Snapshot parquet files with no live counterpart are removed.
    """
    if freeze_date > last_complete_day(today):
        raise ValueError(f"{freeze_date} is not a complete UTC day yet")
    problems = mf.verify_manifest(live_dir)
    if problems:
        raise ValueError("live manifest does not match files: " + "; ".join(problems))

    snapshot_dir.mkdir(parents=True, exist_ok=True)
    entries: list[mf.FileEntry] = []
    for live in mf.read_manifest(live_dir):
        df = pd.read_parquet(live_dir / live.path)
        if "date" in df.columns:
            df = df[df["date"] <= freeze_date].reset_index(drop=True)
        if df.empty:
            continue
        out = snapshot_dir / live.path
        write_parquet_atomic(df, out)
        end = min(live.date_range[1], freeze_date.isoformat()) if live.date_range else None
        date_range = (live.date_range[0], end) if live.date_range and end else None
        entry = mf.make_entry(
            snapshot_dir,
            out,
            source=live.source,
            pulled_at_utc=live.pulled_at_utc,
            query_file=live.query_file,
            date_range=date_range,
            query_sha256=live.query_sha256,
        )
        entries.append(entry)
    keep = {e.path for e in entries}
    for stale in snapshot_dir.glob("*.parquet"):
        if stale.name not in keep:
            stale.unlink()
    mf.write_manifest(snapshot_dir, entries)
    return entries
