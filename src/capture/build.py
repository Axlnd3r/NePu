"""Rebuild every metric from data/<source>/ into site/public/data/*.json.

Writes meta.json (build time, git commit, source), coverage.json (coverage ratio, break-even
volume, sensitivity grid, monthly reconciliation), distribution.json (who brings volume and fees,
concentration) and developer.json (new-contract cohorts, lead/lag). Only meta.json has a
timestamp, so the same input data always gives the same other files.
"""

from __future__ import annotations

import json
import math
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from capture import config
from capture import manifest as mf
from capture.models import breakeven, coverage, developer, distribution

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


EXPLORER_TABLES = (
    "explorer_1click_daily",
    "explorer_channels_daily",
    "explorer_recipients_daily",
    "token_assets",
)
DEVELOPER_TABLES = ("contracts_daily", "defillama_intents_daily")


def load_tables(
    data_dir: Path, names: tuple[str, ...] = REQUIRED_TABLES
) -> dict[str, pd.DataFrame]:
    missing = [t for t in names if not (data_dir / f"{t}.parquet").exists()]
    if missing:
        raise FileNotFoundError(f"{data_dir}: missing table(s) {', '.join(missing)}")
    return {t: pd.read_parquet(data_dir / f"{t}.parquet") for t in names}


def manifest_inputs(data_dir: Path, names: tuple[str, ...]) -> list[dict]:
    """The manifest entries of the tables a payload was built from (hash, range, query)."""
    used = {f"{t}.parquet" for t in names}
    return [
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

    reconciliation = coverage.monthly_reconciliation(inputs)
    return {
        "schema_version": 1,
        "source": f"data/{source}",
        "inputs": manifest_inputs(data_dir, REQUIRED_TABLES),
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


DISTRIBUTION_DEFINITIONS = {
    "channel": "the transaction's referral value; transactions without one are '(none)'",
    "volume_usd": "sum of amountInUsd of successful 1Click transactions (origin side)",
    "fee_usd": "declared app fee: amountInUsd x fee bps, before the 50/50 split with 1Click",
    "share": "channel (or asset) volume / total volume of the period",
    "hhi": "sum of squared shares, between 1/n and 1",
    "top5_share": "sum of the five largest shares",
    "asset": "symbol of the origin asset (same symbol on several chains is one asset)",
    "declared_fee_share_to_near": "declared fee to a NEAR revenue wallet / all declared fee",
    "attributable_share": "declared fee to NEAR revenue wallets / on-chain revenue, same days",
    "near_wallet_only_share": (
        "volume of transactions whose fee recipients are only NEAR revenue wallets; a proxy, "
        "not near.com"
    ),
    "no_app_fee_share": "volume of transactions with no app fee",
    "explorer_share_of_defillama_volume": "Explorer volume / DefiLlama volume on the same days",
    "take_rate": "DefiLlama fees (or revenue) / volume, summed over a month",
}
DISTRIBUTION_NOTES = [
    "Explorer data covers 1Click transactions only, a fraction of Intents volume "
    "(explorer_share_of_defillama_volume); everything below describes that fraction.",
    "near.com cannot be identified: the front-end wallet is almost never an app-fee recipient. "
    "near_wallet_only_share is a proxy for NEAR-run flow and is not called near.com.",
    "Most on-chain NEAR revenue is not explained by app fees to NEAR wallets "
    "(attributable_share); the rest has no per-transaction source in this data.",
    "Declared fees are requested amounts; with a partner key they are split with 1Click.",
    "A transaction with several fee recipients counts in each recipient's volume, so "
    "recipient volumes do not add up; channel and asset volumes do.",
    "The stablecoin list is a judgment on the 1Click token list; see stablecoin_symbols.",
]
DEVELOPER_NOTES = [
    "A new contract is an account whose first deploy comes after a 30-day burn-in from the "
    "start of the data and which had no earlier row. A deploy can also be an upgrade.",
    "Active in a month means at least one FUNCTION_CALL received in it (cohorts_strict: at least "
    "ten). Calls by the deployer count; unique callers are not additive across days, unused.",
    "Cohort sizes can jump when one parent account deploys many sub-accounts; top_parent_share "
    "shows how much of a cohort comes from one parent.",
    "The lead/lag test compares two short monthly series. Few points mean low power; a null "
    "result is the expected outcome and is reported as such. It does not show cause or effect.",
]
SPLIT_MONTH = "2026-05"
TOP_CHANNELS = 25
TOP_ASSETS = 15


def _frame_records(df: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


def distribution_payload(data_dir: Path, source: str) -> dict:
    """distribution.json: Explorer tables when present, otherwise only DefiLlama take rates."""
    defillama = load_tables(data_dir, ("defillama_intents_daily",))["defillama_intents_daily"]
    payload: dict = {
        "schema_version": 1,
        "source": f"data/{source}",
        "definitions": DISTRIBUTION_DEFINITIONS,
        "stablecoin_symbols": sorted(distribution.STABLECOIN_SYMBOLS),
        "near_revenue_wallets": sorted(distribution.NEAR_WALLETS),
        "take_rates": {"monthly": _frame_records(distribution.take_rates(defillama))},
    }
    if not all((data_dir / f"{t}.parquet").exists() for t in EXPLORER_TABLES):
        payload.update(
            {
                "inputs": manifest_inputs(data_dir, ("defillama_intents_daily",)),
                "scope": {"explorer_available": False},
                "notes": [
                    "Explorer tables are not available in this data directory, so only DefiLlama "
                    "take rates are shown: fees and revenue divided by volume, per month. They "
                    "say nothing about channels, assets or who receives the fees."
                ],
            }
        )
        return payload

    names = (*EXPLORER_TABLES, *REQUIRED_TABLES)
    tables = load_tables(data_dir, names)
    daily, channels, recipients = (tables[t] for t in EXPLORER_TABLES[:3])
    dates = pd.to_datetime(daily["date"])
    first, last = dates.min(), dates.max()
    inputs = coverage.build_inputs({t: tables[t] for t in REQUIRED_TABLES})
    onchain_usd = (
        coverage.onchain_revenue_near(inputs[[c for c in inputs.columns if c.startswith("chg_")]])
        * inputs["near_usd"]
    )

    by_symbol_input = distribution.symbols(daily, tables["token_assets"])
    periods: dict[str, list[dict]] = {}
    channel_rows: dict[str, list[dict]] = {}
    asset_rows: dict[str, list[dict]] = {}
    for freq in ("month", "week"):
        ch = distribution.volume_shares(channels, "referral", freq)
        assets = distribution.volume_shares(by_symbol_input, "symbol", freq)
        totals = ch.groupby("period")[["volume_usd", "fee_usd", "tx_count"]].sum().reset_index()
        table = distribution.period_table(list(ch["period"].unique()), freq, first, last)
        for part in (
            totals,
            distribution.concentration(ch, "channel"),
            distribution.concentration(assets, "asset"),
            distribution.asset_categories(assets),
            distribution.near_wallet_shares(daily, freq),
            distribution.near_attribution(recipients, onchain_usd, freq),
            distribution.explorer_coverage(daily, defillama, freq),
        ):
            table = table.merge(part, on="period", how="left")
        periods[freq] = _frame_records(table)
        channel_rows[freq] = _frame_records(
            distribution.top_with_other(ch, "referral", TOP_CHANNELS)
        )
        asset_rows[freq] = _frame_records(distribution.top_with_other(assets, "symbol", TOP_ASSETS))

    overall = distribution.explorer_coverage(
        daily.assign(date=dates.dt.normalize()), defillama, "month"
    )
    payload.update(
        {
            "inputs": manifest_inputs(data_dir, names),
            "scope": {
                "explorer_available": True,
                "first_date": first.date().isoformat(),
                "last_date": last.date().isoformat(),
                "days": int(dates.nunique()),
                "covers": "1Click transactions only",
                "explorer_share_of_defillama_volume_by_month": _frame_records(overall),
                "near_com": {
                    "measured": False,
                    "reason": "no field identifies near.com; the front-end wallet is hardly "
                    "ever an app-fee recipient in these transactions",
                    "proxy": "near_wallet_only_share (see definitions)",
                },
            },
            "notes": DISTRIBUTION_NOTES,
            "periods": periods,
            "channels": channel_rows,
            "assets": asset_rows,
        }
    )
    return payload


def developer_payload(data_dir: Path, source: str) -> dict:
    """developer.json: monthly cohorts of new contracts and the lead/lag test."""
    tables = load_tables(data_dir, DEVELOPER_TABLES)
    contracts, llama = tables["contracts_daily"], tables["defillama_intents_daily"]
    last_date = pd.to_datetime(contracts["date"]).max()
    new = developer.new_contracts(contracts)
    cohorts = developer.cohort_table(contracts, new, last_date)
    strict = developer.cohort_table(contracts, new, last_date, min_calls=developer.MIN_CALLS_STRICT)
    x, y = developer.retained_new_contracts(cohorts), developer.monthly_revenue(llama)
    table = developer.lead_lag(x, y, SPLIT_MONTH, seed=config.RANDOM_SEED)
    series = pd.DataFrame({"retained_new_contracts": x, "revenue_usd": y}).sort_index()
    series.index = series.index.astype(str)
    return {
        "schema_version": 1,
        "source": f"data/{source}",
        "inputs": manifest_inputs(data_dir, DEVELOPER_TABLES),
        "window": {
            "first_date": pd.to_datetime(contracts["date"]).min().date().isoformat(),
            "last_date": last_date.date().isoformat(),
            "burn_in_days": developer.BURN_IN_DAYS,
        },
        "exclusions": {k: int(v) for k, v in new.attrs.items()},
        "definitions": {
            "cohort": "calendar month of a new contract's first deploy",
            "retained": "at least one FUNCTION_CALL in month +k (empty if month +k is incomplete)",
            "retained_new_contracts": "contracts first deployed in month t-1, still called in t",
        },
        "notes": DEVELOPER_NOTES,
        "cohorts": _frame_records(cohorts),
        "cohorts_strict": {"min_calls": developer.MIN_CALLS_STRICT, "rows": _frame_records(strict)},
        "monthly_series": records(series, "month"),
        "lead_lag": {
            "x": "retained_new_contracts",
            "y": "Intents revenue (DefiLlama, USD)",
            "split_month": SPLIT_MONTH,
            "lags_in_months": list(developer.LAGS),
            "rows": _frame_records(table),
            "verdict": developer.verdict(table),
        },
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
    data_dir = ROOT / "data" / source
    return [
        write_json(out_dir / "meta.json", meta),
        write_json(out_dir / "coverage.json", coverage_payload(data_dir, source)),
        write_json(out_dir / "distribution.json", distribution_payload(data_dir, source)),
        write_json(out_dir / "developer.json", developer_payload(data_dir, source)),
    ]
