"""Pre-registered forward tests: written before their windows close, hashed, anchored on NEAR.

`write` freezes data/prereg/tests.json and PREREG.md from the current snapshot (the thresholds are
derived from it, so no number is typed by hand) and refuses to overwrite them. `anchor` commits the
SHA-256 of data/prereg/manifest.json to the proof contract, so the registration time is fixed by a
block. `score` evaluates each test whose window has closed and writes data/prereg/scores.json;
a test whose data is not available yet stays "pending". Every rule reads a quantity this project
already publishes, never a price.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from capture import config
from capture import manifest as mf

PREREG = config.ROOT / "data" / "prereg"
TESTS = PREREG / "tests.json"
DOC = PREREG / "PREREG.md"
SCORES = PREREG / "scores.json"
BAND = (0.5, 2.0)  # a forecast band: half to twice the value measured at registration


def run_id(sha256: str, day: str) -> str:
    return f"prereg-{day}-{sha256[:12]}"


def build_tests(
    *,
    registered_at: str,
    inflow_per_day: float,
    inflow_base: tuple[str, str],
    cr_float_30: float,
    cr_date: str,
    routing: float,
    routing_end: str,
    tolerance: float,
    hsp029_status: str,
    hsp029_block: int,
) -> dict:
    """The registered tests. Every number is an argument, read from the data by the caller."""
    low, high = BAND
    days = 4
    return {
        "registered_at_utc": registered_at,
        "band": list(BAND),
        "tests": [
            {
                "id": "T1",
                "claim": "Fee revenue keeps reaching the buyback wallet at about the recent rate.",
                "quantity": (
                    "NEAR received by buybacks.multisignature.near from intents.near, summed over "
                    "the balance changes NearBlocks lists in the window"
                ),
                "window": ["2026-11-10T00:00:00Z", "2026-11-14T00:00:00Z"],
                "base": {
                    "near_per_day": inflow_per_day,
                    "days": days,
                    "measured_over": list(inflow_base),
                },
                "pass_if": [inflow_per_day * days * low, inflow_per_day * days * high],
                "scored_on": "2026-11-14",
            },
            {
                "id": "T2",
                "claim": "Not yet: buybacks and burn stay far from covering issuance.",
                "quantity": "CR_float over 30 days in NEAR units (coverage.json cr_float_30)",
                "window": ["2026-11-01", "2026-11-30"],
                "base": {"value": cr_float_30, "date": cr_date},
                "pass_if": [cr_float_30 * low, min(cr_float_30 * high, 1.0)],
                "scored_on": "first snapshot that covers 2026-11-30",
            },
            {
                "id": "T3",
                "claim": "Most protocol revenue reaching NEAR wallets goes to the buyback wallet.",
                "quantity": (
                    "buyback wallet inflow / on-chain revenue of the three revenue wallets, USD at "
                    "daily prices, 30 days (summary.ledger.kept.buyback_of_onchain)"
                ),
                "window": ["2026-11-01", "2026-11-30"],
                "base": {"value": routing, "date": routing_end},
                "pass_if": [routing * low, 1.0],
                "scored_on": "first snapshot that covers 2026-11-30",
            },
            {
                "id": "T4",
                "claim": "The measurement keeps holding: on-chain revenue matches DefiLlama.",
                "quantity": "absolute deviation of on-chain from DefiLlama revenue, month 2026-11",
                "window": ["2026-11-01", "2026-11-30"],
                "base": {"tolerance": tolerance},
                "pass_if": [0.0, tolerance],
                "scored_on": "first snapshot that covers 2026-11-30",
            },
            {
                "id": "T5",
                "claim": "The HSP-029 issuance cut is not rejected or vetoed in its timelock.",
                "quantity": "vote.dao get_proposal(29): rejecter_id and status",
                "window": [registered_at, "2026-11-17T00:00:00Z"],
                "base": {"status": hsp029_status, "block": hsp029_block},
                "pass_if": "rejecter_id is null and the status is neither a rejection nor a veto",
                "scored_on": "2026-11-17",
            },
        ],
    }


def render_doc(tests: dict) -> str:
    """PREREG.md: the same tests in words. Generated, frozen with tests.json."""
    lines = [
        "# Pre-registered forward tests",
        "",
        f"Registered {tests['registered_at_utc']}, before any window closed. T1 and T5 start at or "
        "after the registration. T2 to T4 cover November 2026; the days of it before the "
        "registration were already on chain but not in this project's data (its snapshot ends "
        "2026-11-01), and the bands are set from October. "
        "Generated by `capture prereg write` from the snapshot; frozen. The SHA-256 of "
        "`data/prereg/manifest.json` (which holds the hash of this file and of `tests.json`) is "
        "committed to the proof contract on NEAR; `capture prereg score` evaluates them. A miss is "
        "reported as a miss. No test is about a price.",
        "",
    ]
    for t in tests["tests"]:
        rule = t["pass_if"]
        if isinstance(rule, list):
            rule = f"between {rule[0]:.6g} and {rule[1]:.6g}"
        lines += [
            f"## {t['id']}: {t['claim']}",
            "",
            f"- Quantity: {t['quantity']}.",
            f"- Window: {t['window'][0]} to {t['window'][1]}.",
            f"- At registration: {json.dumps(t['base'])}.",
            f"- Passes if: {rule}.",
            f"- Scored: {t['scored_on']}.",
            "",
        ]
    return "\n".join(lines)


def write(tests: dict, directory: Path = PREREG) -> list[Path]:
    """Freeze the tests. Refuses to overwrite: a registration is written once."""
    tests_file, doc = directory / TESTS.name, directory / DOC.name
    if tests_file.exists() or doc.exists():
        raise FileExistsError(f"{directory} already holds a registration; it is frozen")
    directory.mkdir(parents=True, exist_ok=True)
    tests_file.write_text(json.dumps(tests, indent=1) + "\n", encoding="utf-8", newline="\n")
    doc.write_text(render_doc(tests), encoding="utf-8", newline="\n")
    when = tests["registered_at_utc"]
    entries = [
        mf.make_entry(directory, f, source="capture prereg write", pulled_at_utc=when)
        for f in (tests_file, doc)
    ]
    mf.write_manifest(directory, entries)
    return [tests_file, doc, directory / mf.MANIFEST_NAME]


def manifest_sha256(directory: Path = PREREG) -> str:
    return mf.sha256_file(directory / mf.MANIFEST_NAME)


# ---------------------------------------------------------------- scoring
def _verdict(value: float, band: list[float]) -> str:
    return "pass" if band[0] <= value <= band[1] else "miss"


def score_t1(test: dict, changes: pd.DataFrame | None) -> dict:
    if changes is None:
        return {"status": "pending", "reason": "no activity file"}
    start, end = (pd.Timestamp(x).tz_localize(None) for x in test["window"])
    covered = changes["timestamp"].max() if "timestamp" in changes else None
    if covered is None or covered < end:
        return {"status": "pending", "reason": "the activity file does not reach the window end"}
    inside = changes[(changes["timestamp"] >= start) & (changes["timestamp"] < end)]
    value = float(
        inside.loc[(inside["kind"] == "intents") & (inside["change_near"] > 0), "change_near"].sum()
    )
    return {"status": _verdict(value, test["pass_if"]), "value": value}


def score_t5(test: dict, proposal: dict | None, read_at: str | None) -> dict:
    if proposal is None or read_at is None or read_at < test["window"][1]:
        return {"status": "pending", "reason": "read the proposal after the window closes"}
    status = str(proposal["status"])
    ok = proposal.get("rejecter_id") is None and not any(
        w in status.lower() for w in ("reject", "veto")
    )
    return {"status": "pass" if ok else "miss", "value": status}


def score_series(test: dict, value_on: Callable[[str], float | None]) -> dict:
    value = value_on(test["window"][1])
    if value is None:
        return {"status": "pending", "reason": "no snapshot covers the window end yet"}
    return {"status": _verdict(value, test["pass_if"]), "value": value}


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
