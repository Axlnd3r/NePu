"""Write, read and verify data/<dir>/manifest.json.

Every data file shown anywhere in the project must be listed in a manifest with its
SHA-256, row count, source, query file, block_date range and pull time (UTC).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pyarrow.parquet as pq

MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True)
class FileEntry:
    path: str  # relative to the manifest's directory, POSIX separators
    sha256: str
    rows: int | None
    source: str
    query_file: str | None
    date_range: tuple[str, str] | None  # inclusive block_date range, ISO dates
    pulled_at_utc: str  # ISO 8601, e.g. 2026-11-02T08:00:00Z
    query_sha256: str | None = None  # SHA-256 of the query file when the data was pulled


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def count_rows(path: Path) -> int | None:
    """Row count for known tabular formats, None otherwise."""
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pq.ParquetFile(path).metadata.num_rows
    if suffix == ".csv":
        with path.open("rb") as f:
            return max(sum(1 for _ in f) - 1, 0)
    return None


def make_entry(
    data_dir: Path,
    file_path: Path,
    *,
    source: str,
    pulled_at_utc: str,
    query_file: str | None = None,
    date_range: tuple[str, str] | None = None,
    query_sha256: str | None = None,
) -> FileEntry:
    return FileEntry(
        path=file_path.relative_to(data_dir).as_posix(),
        sha256=sha256_file(file_path),
        rows=count_rows(file_path),
        source=source,
        query_file=query_file,
        date_range=date_range,
        pulled_at_utc=pulled_at_utc,
        query_sha256=query_sha256,
    )


def write_manifest(data_dir: Path, entries: list[FileEntry]) -> Path:
    out = data_dir / MANIFEST_NAME
    payload = {"files": [asdict(e) for e in sorted(entries, key=lambda e: e.path)]}
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out


def upsert_entries(data_dir: Path, entries: list[FileEntry]) -> Path:
    """Add or replace entries (matched by path) and rewrite the manifest."""
    exists = (data_dir / MANIFEST_NAME).exists()
    by_path = {e.path: e for e in read_manifest(data_dir)} if exists else {}
    by_path.update({e.path: e for e in entries})
    return write_manifest(data_dir, list(by_path.values()))


def read_manifest(data_dir: Path) -> list[FileEntry]:
    payload = json.loads((data_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    entries = []
    for raw in payload["files"]:
        dr = raw.get("date_range")
        entries.append(FileEntry(**{**raw, "date_range": tuple(dr) if dr else None}))
    return entries


def verify_manifest(data_dir: Path) -> list[str]:
    """Recompute hashes and row counts. Returns a list of problems (empty = OK)."""
    problems = []
    for e in read_manifest(data_dir):
        f = data_dir / e.path
        if not f.is_file():
            problems.append(f"{e.path}: missing")
            continue
        actual = sha256_file(f)
        if actual != e.sha256:
            problems.append(f"{e.path}: sha256 {actual} != manifest {e.sha256}")
            continue  # a changed file may no longer parse; the hash mismatch is enough
        rows = count_rows(f)
        if rows != e.rows:
            problems.append(f"{e.path}: rows {rows} != manifest {e.rows}")
    return problems
