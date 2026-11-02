"""Rebuild every metric from data/<source>/ into site/public/data/*.json.

Writes meta.json (build time, git commit, source) and coverage.json (coverage ratio, break-even
volume, sensitivity grid, monthly reconciliation). coverage.json has no timestamps, so the same
input data always gives the same file.
"""

from __future__ import annotations

import json
import math
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from capture import manifest as mf
from capture.models import breakeven, coverage

ROOT = Path(__file__).resolve().parents[2]
SITE_DATA = ROOT / "site" / "public" / "data"
REQUIRED_TABLES = (
    "supply_daily",
    "price_daily",
    "defillama_intents_daily",
    "fee_wallet_inflows_daily",
)
TAU_WINDOW = 30
# Series that are reported with their first and last non-empty date.
AVAILABILITY_METRICS = (
    "issuance_gross_near",
    "buyback_near",
    "buyback_near_proxy",
    "cr_float_7",
    "cr_float_30",
    "cr_float_90",
    "cr_supply_30",
    "cr_float_usd_30",
    "cr_float_proxy_30",
    "tau_eff_30",
    "v_star",
)
DEFINITIONS = {
    "issuance_gross_near": "total_supply(d) - total_supply(d-1) + burnt_near(d)",
    "buyback_near": (
        "NEAR received by buybacks.multisignature.near from outside the revenue wallets: positive "
        "part of its daily net balance change minus estimated transfers from the other revenue "
        "wallets"
    ),
    "buyback_near_proxy": (
        "DefiLlama holders_revenue_usd(d) / near_usd(d); a proxy, not a measurement"
    ),
    "cr_float": (
        "sum(buyback_near + burnt_near) / sum(issuance_gross_near) over the window, in NEAR"
    ),
    "cr_supply": "sum(burnt_near) / sum(issuance_gross_near); buybacks do not reduce total supply",
    "cr_float_usd": "cr_float with each day valued at that day's NEAR price",
    "tau_eff": "sum(DefiLlama revenue_usd) / sum(DefiLlama volume_usd) over the window",
    "v_star": (
        "(30d avg issuance_gross_near x near_usd(d) - 30d avg burnt_usd) / tau_eff(d, 30), "
        "in USD of daily Intents volume"
    ),
}
NOTES = [
    "Buyback series start on the first day after the buyback wallet first appears in the data; "
    "earlier periods are empty because the buyback destination is unknown (DATA_AUDIT.md check 5).",
    "Wallet changes are net daily balance changes; transfers between revenue wallets are estimated "
    "from same-day moves and validated against receipts on the days that mattered.",
    "tau_eff counts all captured revenue, while buyback_near counts only the buyback wallet, so "
    "v_star is optimistic; v_star_buyback_variant uses the buyback wallet only.",
    "USD views need a price; prices exist only for the past 365 days of the pull (DATA_AUDIT.md).",
    "Gross issuance is derived from net supply plus burn; daily values are lumpy (epoch minting).",
]


def git_commit(root: Path = ROOT) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def load_tables(data_dir: Path) -> dict[str, pd.DataFrame]:
    missing = [t for t in REQUIRED_TABLES if not (data_dir / f"{t}.parquet").exists()]
    if missing:
        raise FileNotFoundError(f"{data_dir}: missing table(s) {', '.join(missing)}")
    return {t: pd.read_parquet(data_dir / f"{t}.parquet") for t in REQUIRED_TABLES}


def _clean(value: object) -> object:
    """JSON-safe: NaN/NaT -> None, numpy scalars -> Python, timestamps -> ISO dates."""
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, float | int) or hasattr(value, "item"):
        number = value.item() if hasattr(value, "item") else value
        return None if isinstance(number, float) and math.isnan(number) else number
    return None if value is pd.NaT or value is None else value


def records(df: pd.DataFrame, index_name: str) -> list[dict]:
    frame = df.reset_index().rename(columns={df.index.name or "index": index_name})
    return [{k: _clean(v) for k, v in row.items()} for row in frame.to_dict(orient="records")]


def availability(table: pd.DataFrame) -> dict[str, dict[str, str | None]]:
    out: dict[str, dict[str, str | None]] = {}
    for metric in AVAILABILITY_METRICS:
        first, last = table[metric].first_valid_index(), table[metric].last_valid_index()
        out[metric] = {
            "first_date": None if first is None else first.date().isoformat(),
            "last_date": None if last is None else last.date().isoformat(),
        }
    return out


def coverage_payload(data_dir: Path, source: str) -> dict:
    tables = load_tables(data_dir)
    inputs = coverage.build_inputs(tables)
    table = coverage.coverage_table(inputs)
    changes = inputs[[c for c in inputs.columns if c.startswith("chg_")]]
    buyback = table["buyback_near"]

    table["v_star"] = breakeven.v_star(
        table["issuance_gross_near"], table["burnt_near"], table["near_usd"], table["tau_eff_30"]
    )
    tau_bb = breakeven.tau_eff_buyback(buyback, table["near_usd"], inputs["volume_usd"], TAU_WINDOW)
    table["tau_eff_buyback_30"] = tau_bb
    table["v_star_buyback_variant"] = breakeven.v_star(
        table["issuance_gross_near"], table["burnt_near"], table["near_usd"], tau_bb
    )
    table["volume_usd_30d_avg"] = (
        inputs["volume_usd"].rolling(TAU_WINDOW, min_periods=TAU_WINDOW).mean()
    )

    as_of = table["v_star"].last_valid_index()
    grid = None
    if as_of is not None:
        burn_avg = table["burnt_near"].rolling(TAU_WINDOW, min_periods=TAU_WINDOW).mean()
        grid = {
            "as_of": as_of.date().isoformat(),
            "inputs": {
                "total_supply_near": float(table.loc[as_of, "total_supply_near"]),
                "near_usd": float(table.loc[as_of, "near_usd"]),
                "burnt_near_30d_avg": float(burn_avg.loc[as_of]),
                "tau_eff_30": float(table.loc[as_of, "tau_eff_30"]),
            },
            "grid": records(
                breakeven.sensitivity_grid(
                    float(table.loc[as_of, "total_supply_near"]),
                    float(table.loc[as_of, "near_usd"]),
                    float(burn_avg.loc[as_of]),
                    float(table.loc[as_of, "tau_eff_30"]),
                ),
                "row",
            ),
        }

    latest = {}
    for metric in (
        "cr_float_30",
        "cr_float_90",
        "cr_supply_30",
        "cr_float_proxy_30",
        "tau_eff_30",
        "v_star",
    ):
        last = table[metric].last_valid_index()
        if last is not None:
            latest[metric] = {
                "date": last.date().isoformat(),
                "value": _clean(table.loc[last, metric]),
            }

    used = {f"{t}.parquet" for t in REQUIRED_TABLES}
    manifest_inputs = [
        {
            "path": e.path,
            "sha256": e.sha256,
            "rows": e.rows,
            "date_range": e.date_range,
            "source": e.source,
            "query_file": e.query_file,
            "query_sha256": e.query_sha256,
            "pulled_at_utc": e.pulled_at_utc,
        }
        for e in mf.read_manifest(data_dir)
        if e.path in used
    ]
    reconciliation = coverage.monthly_reconciliation(inputs)
    return {
        "schema_version": 1,
        "source": f"data/{source}",
        "inputs": manifest_inputs,
        "windows": list(coverage.WINDOWS),
        "buyback_wallet": coverage.BUYBACK_WALLET,
        "definitions": DEFINITIONS,
        "notes": NOTES,
        "availability": availability(table),
        "latest": latest,
        "series": records(table, "date"),
        "break_even": {"sensitivity": grid, "tau_window": TAU_WINDOW},
        "reconciliation": {
            "tolerance": coverage.RECONCILIATION_TOLERANCE,
            "months": records(reconciliation, "month"),
        },
        "wallet_columns": list(changes.columns),
    }


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, allow_nan=False, indent=1) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def build(source: str, out_dir: Path = SITE_DATA) -> list[Path]:
    meta = {
        "built_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_commit": git_commit(),
        "source": f"data/{source}",
    }
    payload = coverage_payload(ROOT / "data" / source, source)
    return [write_json(out_dir / "meta.json", meta), write_json(out_dir / "coverage.json", payload)]
