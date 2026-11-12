"""build.py: coverage.json is valid JSON, deterministic, and every text file uses LF."""

import json
from pathlib import Path

import pytest

from capture.build import build, coverage_payload, write_json
from capture.config import DATA_SNAPSHOT, ROOT

TEXT_SUFFIXES = {".py", ".md", ".json", ".sql", ".yml", ".yaml", ".toml", ".ts", ".tsx", ".css"}
TEXT_ROOTS = ("src", "tests", "sql", "docs", "data/snapshot", ".github", "site/app")


@pytest.fixture(scope="module")
def payload() -> dict:
    return coverage_payload(DATA_SNAPSHOT, "snapshot")


def test_payload_is_json_safe_and_complete(payload: dict) -> None:
    text = json.dumps(payload, allow_nan=False)  # raises on NaN or infinity
    assert json.loads(text)["schema_version"] == 1
    assert {
        "inputs",
        "series",
        "availability",
        "latest",
        "break_even",
        "reconciliation",
    } <= payload.keys()
    assert {i["path"] for i in payload["inputs"]} == {
        "supply_daily.parquet",
        "price_daily.parquet",
        "defillama_intents_daily.parquet",
        "fee_wallet_inflows_daily.parquet",
    }
    assert all(i["sha256"] for i in payload["inputs"])
    assert payload["reconciliation"]["tolerance"] == 0.15


def test_build_is_deterministic(payload: dict, tmp_path: Path) -> None:
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    write_json(first, payload)
    write_json(second, coverage_payload(DATA_SNAPSHOT, "snapshot"))
    assert first.read_bytes() == second.read_bytes()
    assert b"\r" not in first.read_bytes()


def test_series_has_one_row_per_day_with_iso_dates(payload: dict) -> None:
    dates = [row["date"] for row in payload["series"]]
    assert dates == sorted(set(dates))
    assert all(len(d) == 10 and d[4] == "-" for d in dates)


def test_no_crlf_in_project_text_files() -> None:
    offenders = []
    for root in TEXT_ROOTS:
        base = ROOT / root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in TEXT_SUFFIXES and b"\r\n" in path.read_bytes():
                offenders.append(path.relative_to(ROOT).as_posix())
    assert not offenders, f"CRLF line endings (use LF, see .gitattributes): {offenders}"


def test_every_payload_is_deterministic_and_has_lf_endings(tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    written = build("snapshot", first)
    build("snapshot", second)
    names = sorted(p.relative_to(first).as_posix() for p in written)
    assert names == [
        "README.md",  # upper case sorts before the rest
        "THESIS.md",
        "coverage.json",
        "developer.json",
        "distribution.json",
        "markers.json",
        "meta.json",
        "prereg.json",
        "proof/manifest.json.ots",
        "provenance.json",
        "queries.json",
        "snapshot-manifest.json",
        "summary.json",
        "usage.json",
        "valuation.json",
    ]
    for name in names:
        if not name.endswith(".ots"):  # a binary file may hold a 0x0d byte; text must not
            assert b"\r" not in (first / name).read_bytes()
        if name != "meta.json":  # meta.json carries the build time
            assert (first / name).read_bytes() == (second / name).read_bytes(), name
