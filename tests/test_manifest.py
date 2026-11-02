from pathlib import Path

import pandas as pd
import pytest

from capture.manifest import (
    make_entry,
    read_manifest,
    sha256_file,
    verify_manifest,
    write_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
COMMITTED_MANIFESTS = sorted((ROOT / "data").glob("*/manifest.json"))


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    df = pd.DataFrame({"block_date": ["2026-11-01", "2026-11-02"], "value": [1.0, 2.0]})
    df.to_parquet(tmp_path / "daily.parquet", index=False)
    entry = make_entry(
        tmp_path,
        tmp_path / "daily.parquet",
        source="test",
        query_file="sql/test.sql",
        date_range=("2026-11-01", "2026-11-02"),
        pulled_at_utc="2026-11-02T00:00:00Z",
    )
    write_manifest(tmp_path, [entry])
    return tmp_path


def test_roundtrip_hashes_match(data_dir: Path) -> None:
    [entry] = read_manifest(data_dir)
    assert entry.rows == 2
    assert entry.date_range == ("2026-11-01", "2026-11-02")
    assert entry.sha256 == sha256_file(data_dir / entry.path)
    assert verify_manifest(data_dir) == []


def test_tampered_file_detected(data_dir: Path) -> None:
    f = data_dir / "daily.parquet"
    raw = bytearray(f.read_bytes())
    raw[len(raw) // 2] ^= 0xFF
    f.write_bytes(bytes(raw))
    assert any("sha256" in p for p in verify_manifest(data_dir))


def test_truncated_file_reported_not_raised(data_dir: Path) -> None:
    f = data_dir / "daily.parquet"
    f.write_bytes(f.read_bytes()[:-8])  # breaks the parquet footer
    [problem] = verify_manifest(data_dir)
    assert "sha256" in problem


def test_missing_file_detected(data_dir: Path) -> None:
    (data_dir / "daily.parquet").unlink()
    assert verify_manifest(data_dir) == ["daily.parquet: missing"]


@pytest.mark.parametrize("manifest", COMMITTED_MANIFESTS, ids=lambda p: p.parent.name)
def test_committed_manifest_hashes(manifest: Path) -> None:
    assert verify_manifest(manifest.parent) == []


def test_manifest_is_written_with_lf_line_endings(data_dir: Path) -> None:
    assert b"\r" not in (data_dir / "manifest.json").read_bytes()
