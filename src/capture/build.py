"""Rebuild every metric from data/<source>/ into site/public/data/*.json.

Writes meta.json (build time, git commit, source), coverage.json (coverage ratio, break-even
volume, sensitivity grid, monthly reconciliation), distribution.json (who brings volume and fees,
concentration) and developer.json (new-contract cohorts, lead/lag). Only meta.json has a
timestamp, so the same input data always gives the same other files.
"""

from __future__ import annotations

import csv
import json
import math
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from capture import config, thesis
from capture import manifest as mf
from capture import proof as proof_mod
from capture.models import breakeven, coverage, developer, distribution, ledger, valuation

ROOT = Path(__file__).resolve().parents[2]
SITE_DATA = ROOT / "site" / "public" / "data"
REFERENCE = ROOT / "data" / "reference"
PROOF_FILE = ROOT / "data" / "proof.json"  # written by `make proof` (F7)
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
    for column in ("volume_usd", "fees_usd", "revenue_usd"):
        table[column] = inputs[column]
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


VALUATION_TABLES = REQUIRED_TABLES
# Volume growth before this month is the launch phase; reported next to the full-sample mean.
LAUNCH_END = "2025-12"
VALUATION_ASSUMPTIONS = {
    "price": (
        "The NEAR price in USD is held constant at its latest value in every run. This isolates "
        "volume, take rate and inflation; it is not a forecast and no price level is predicted. "
        "The 0.5x and 2x runs are sensitivities to that assumption."
    ),
    "supply": "Total supply is held at its latest value, as in V*; real supply grows.",
    "burn": "Gas burn is held at its 30-day average in NEAR per day.",
    "volume": (
        "Start: the 30-day average daily Intents volume (DefiLlama). Each month multiplies it by "
        "exp(growth); growth is bootstrapped from monthly log changes of the monthly average "
        "since 2025-06, in blocks of 3 months."
    ),
    "tau": (
        "Buyback take rate (buyback wallet inflow / Intents volume, the basis of CR_float), one "
        "value per path drawn uniformly between the lowest and highest observed monthly value."
    ),
    "inflation": (
        "Two annual rates: 2.5 % constant (observed net supply growth is about 2.5 %, "
        "DATA_AUDIT.md Check 6), and the HSP-029 proposal: 2.5 % held for a 90-day grace "
        "period, then lowered to 1.6 % over 24 months and held. The proposal steps down every "
        "epoch; a linear monthly ramp approximates it. HSP-029 went to a vote in October 2026 "
        "and its result is not confirmed in our sources (data/reference/parameters.csv, "
        "events.csv)."
    ),
    "scenarios": {
        "historical": "bootstrapped growth as drawn (its drift is the history's)",
        "decay": "zero-mean draws plus the historical drift, which halves every 12 months",
        "flat": "zero-mean draws: no drift, historical volatility",
    },
}
VALUATION_DEFINITIONS = {
    "cr": "(tau x V + burn_near x P) / (inflation x supply / 365 x P), V the 30-day average volume",
    "p_cr_ge_1": "share of paths with CR >= 1 in that month (at that month, not 'ever')",
    "median_first_month": (
        "median over all paths of the first month with CR >= 1; 'not reached' if fewer than "
        "half of the paths get there within the horizon"
    ),
    "fan": "p10, p50 and p90 of CR across paths, months 1 to 60",
    "required_cagr": "annual growth of the 30-day volume needed to reach V* in the horizon",
}
VALUATION_NOTES = [
    "Results are conditional on the stated assumptions, not forecasts; no price is predicted.",
    "The growth sample is short and dominated by the launch phase: see growth.n_months, "
    "growth.mean_all and growth.mean_after_launch.",
    "The historical and decay scenarios inherit a mean growth set by the launch phase; "
    "volume_p50_usd_per_day shows the volume each run implies. A probability close to 1 there "
    "rests on that volume, not on observed behaviour after the launch.",
    "The tau range is the lowest to highest of a few complete months and the latest month is its "
    "maximum, so the drawn tau is below the current one on average and the flat scenario's "
    "median CR starts below the measured CR.",
    "The buyback take rate has few complete months and was rising; its range is crude.",
    "Real supply grows with issuance, which lowers CR slightly: the runs are a bit optimistic.",
    "Buybacks are not burns (CLAUDE.md rule 6): CR is the float view, buyback plus gas burn.",
    "Month 0 at the latest price differs from the measured CR_float because the buyback is USD "
    "converted at that price; at the mean price of the same 30 days the model reproduces it "
    "(start.cr_model_month0_at_window_price). CR in every run is therefore price-dependent.",
]


@dataclass(frozen=True)
class StartState:
    """The measured state every forward-looking view starts from (valuation, ledger, levers)."""

    frame: pd.DataFrame
    table: pd.DataFrame
    as_of: pd.Timestamp
    inputs: valuation.Inputs
    taus: dict[str, float]
    monthly_tau: pd.Series


def start_state(data_dir: Path) -> StartState:
    """Last day on which the 30-day volume, burn, both take rates, CR_float and price all exist."""
    frame = coverage.build_inputs(load_tables(data_dir))
    table = coverage.coverage_table(frame)
    volume, near_usd = frame["volume_usd"], table["near_usd"]
    tau_bb = breakeven.tau_eff_buyback(table["buyback_near"], near_usd, volume, TAU_WINDOW)
    burn_avg = table["burnt_near"].rolling(TAU_WINDOW, min_periods=TAU_WINDOW).mean()
    volume_avg = volume.rolling(TAU_WINDOW, min_periods=TAU_WINDOW).mean()
    ready = pd.concat(
        [tau_bb, burn_avg, volume_avg, table["tau_eff_30"], table["cr_float_30"], near_usd], axis=1
    ).dropna()
    as_of = ready.index[-1]
    monthly_tau = valuation.monthly_tau(table["buyback_near"] * near_usd, volume)
    inputs = valuation.Inputs(
        volume_usd_per_day=float(volume_avg[as_of]),
        total_supply_near=float(table.loc[as_of, "total_supply_near"]),
        near_usd=float(near_usd[as_of]),
        burnt_near_per_day=float(burn_avg[as_of]),
        tau_min=float(monthly_tau.min()),
        tau_max=float(monthly_tau.max()),
    )
    taus = {"buyback": float(tau_bb[as_of]), "revenue": float(table.loc[as_of, "tau_eff_30"])}
    return StartState(frame, table, as_of, inputs, taus, monthly_tau)


def valuation_payload(
    data_dir: Path,
    source: str,
    seed: int = config.RANDOM_SEED,
    n_paths: int = config.MC_PATHS,
) -> dict:
    """valuation.json: reverse break-even table and Monte Carlo of CR_float (no price forecast)."""
    start = start_state(data_dir)
    frame, table, as_of = start.frame, start.table, start.as_of
    inputs, taus, monthly_tau = start.inputs, start.taus, start.monthly_tau
    volume, near_usd = frame["volume_usd"], table["near_usd"]
    reverse = valuation.reverse_table(
        inputs, taus, (config.INFLATION_CURRENT, config.INFLATION_PROPOSAL)
    )

    growth = valuation.monthly_log_growth(volume, pd.Timestamp(config.GROWTH_START))
    inflation_paths = {
        f"constant_{config.INFLATION_CURRENT * 100:g}": valuation.inflation_path(
            config.MC_MONTHS, config.INFLATION_CURRENT
        ),
        f"ramp_to_{config.INFLATION_PROPOSAL * 100:g}": valuation.inflation_path(
            config.MC_MONTHS,
            config.INFLATION_CURRENT,
            config.INFLATION_PROPOSAL,
            config.INFLATION_RAMP_MONTHS,
            config.INFLATION_GRACE_MONTHS,
        ),
    }
    runs = valuation.run_scenarios(
        inputs,
        growth.to_numpy(),
        seed=seed,
        n_paths=n_paths,
        n_months=config.MC_MONTHS,
        block=config.MC_BLOCK_MONTHS,
        half_life_months=config.DECAY_HALF_LIFE_MONTHS,
        inflation_paths=inflation_paths,
    )
    month0 = valuation.cr_paths(
        np.zeros((1, 1)),
        np.array([taus["buyback"]]),
        valuation.inflation_path(1, config.INFLATION_CURRENT),
        inputs,
    )
    window_price = float(near_usd[as_of - pd.Timedelta(days=TAU_WINDOW - 1) : as_of].mean())
    month0_window_price = valuation.cr_paths(
        np.zeros((1, 1)),
        np.array([taus["buyback"]]),
        valuation.inflation_path(1, config.INFLATION_CURRENT),
        inputs,
        price_multiplier=window_price / inputs.near_usd,
    )
    after_launch = growth[growth.index >= pd.Timestamp(f"{LAUNCH_END}-01")]
    return {
        "schema_version": 1,
        "source": f"data/{source}",
        "inputs": manifest_inputs(data_dir, VALUATION_TABLES),
        "seed": seed,
        "n_paths": n_paths,
        "n_months": config.MC_MONTHS,
        "block_months": config.MC_BLOCK_MONTHS,
        "definitions": VALUATION_DEFINITIONS,
        "assumptions": VALUATION_ASSUMPTIONS,
        "start": {
            "as_of": as_of.date().isoformat(),
            "volume_usd_per_day": inputs.volume_usd_per_day,
            "near_usd": inputs.near_usd,
            "total_supply_near": inputs.total_supply_near,
            "burnt_near_per_day": inputs.burnt_near_per_day,
            "tau_buyback_30": taus["buyback"],
            "tau_revenue_30": taus["revenue"],
            "tau_monthly_range": {
                "min": inputs.tau_min,
                "max": inputs.tau_max,
                "months": records(monthly_tau.rename("tau_buyback").to_frame(), "month"),
            },
            "cr_float_30_observed": float(table.loc[as_of, "cr_float_30"]),
            "cr_model_month0": float(month0[0, 0]),
            "near_usd_window_mean": window_price,
            "cr_model_month0_at_window_price": float(month0_window_price[0, 0]),
        },
        "growth": {
            "start": config.GROWTH_START.isoformat(),
            "first_month": growth.index[0].strftime("%Y-%m"),
            "n_months": len(growth),
            "n_blocks_available": len(growth) - config.MC_BLOCK_MONTHS + 1,
            "mean_all": float(growth.mean()),
            "std_all": float(growth.std()),
            "launch_phase_ends": LAUNCH_END,
            "mean_after_launch": float(after_launch.mean()),
            "n_months_after_launch": len(after_launch),
            "rows": records(growth.rename("log_growth").to_frame(), "month"),
        },
        "reverse": {"rows": _frame_records(reverse)},
        "scenarios": runs,
        "notes": VALUATION_NOTES,
    }


LEVERS_NOTE = (
    "Price is not a lever here: buyback and issuance are both valued at the latest NEAR price, and "
    "V* scales with it (see the Valuation Lab sensitivity). Each step keeps the previous ones."
)


def summary_payload(data_dir: Path, source: str) -> dict:
    """summary.json: hero sentence, week-on-week CR, the capture ledger, levers and conditions."""
    start = start_state(data_dir)
    frame, table, inputs, taus = start.frame, start.table, start.inputs, start.taus

    both = table[["cr_float_usd_30", "cr_float_30"]].dropna()
    hero_date = both.index[-1]
    cr_usd = float(both.loc[hero_date, "cr_float_usd_30"])
    day = hero_date.date().isoformat()
    hero = {
        "date": day,
        "cr_float_usd_30": cr_usd,
        "cr_float_30": float(both.loc[hero_date, "cr_float_30"]),
        "sentence": (
            f"For every $1 of new NEAR issued, {round(cr_usd * 100)} cents come back as buybacks "
            f"or gas burn (30 days to {day})."
        ),
    }

    changes = frame[[c for c in frame.columns if c.startswith("chg_")]]
    daily = pd.DataFrame(
        {
            "volume_usd": frame["volume_usd"],
            "fees_usd": frame["fees_usd"],
            "revenue_usd": frame["revenue_usd"],
            "onchain_revenue_near": coverage.onchain_revenue_near(changes),
            "buyback_near": table["buyback_near"],
            "burnt_near": table["burnt_near"],
            "issuance_gross_near": table["issuance_gross_near"],
            "near_usd": table["near_usd"],
        }
    )
    args = (inputs.total_supply_near, inputs.near_usd, inputs.burnt_near_per_day)
    v0 = inputs.volume_usd_per_day
    worst = coverage.monthly_reconciliation(frame)["deviation"].abs().max()
    waterfall = ledger.waterfall(daily, start.as_of, TAU_WINDOW)
    return {
        "schema_version": 1,
        "source": f"data/{source}",
        "inputs": manifest_inputs(data_dir, REQUIRED_TABLES),
        "hero": hero,
        "this_week": ledger.this_week(table["cr_float_30"]),
        "history": {
            "cr_float_30_max": {
                "date": table["cr_float_30"].idxmax().date().isoformat(),
                "value": float(table["cr_float_30"].max()),
            }
        },
        "ledger": waterfall,
        "levers": {
            "as_of": start.as_of.date().isoformat(),
            "volume_usd_per_day": v0,
            "steps": ledger.lever_bridge(
                v0,
                *args,
                tau_buyback=taus["buyback"],
                tau_revenue=taus["revenue"],
                inflation_now=config.INFLATION_CURRENT,
                inflation_target=config.INFLATION_PROPOSAL,
            ),
            "note": LEVERS_NOTE,
        },
        "conditions": ledger.conditions(
            volume=v0,
            v_star=valuation.breakeven_volume(config.INFLATION_CURRENT, *args, taus["buyback"]),
            routed_share=waterfall["kept"]["buyback_of_onchain"],
            worst_deviation=float(worst),
            tolerance=coverage.RECONCILIATION_TOLERANCE,
        ),
    }


def queries_payload(data_dir: Path) -> dict:
    """queries.json: the SQL text (BigQuery tables) or request (APIs) behind every input table."""
    queries = []
    for entry in mf.read_manifest(data_dir):
        table = entry.path.removesuffix(".parquet")
        if entry.query_file:
            text = (ROOT / entry.query_file).read_text(encoding="utf-8")
            queries.append(
                {
                    "id": table,
                    "kind": "bigquery_sql",
                    "file": entry.query_file,
                    "sha256": entry.query_sha256,
                    "text": text,
                }
            )
        else:
            queries.append({"id": table, "kind": "http_api", "file": None, "text": entry.source})
    return {"schema_version": 1, "queries": queries}


def _source_rows(directory: Path) -> list[dict]:
    return [
        {
            "path": e.path,
            "source": e.source,
            "rows": e.rows,
            "date_range": e.date_range,
            "pulled_at_utc": e.pulled_at_utc,
            "sha256": e.sha256,
            "sha256_8": e.sha256[:8],
            "query_file": e.query_file,
        }
        for e in mf.read_manifest(directory)
    ]


def provenance_payload(data_dir: Path, source: str) -> dict:
    """provenance.json: every file with hash and range, reconciliation status, proof of analysis."""
    frame = coverage.build_inputs(load_tables(data_dir))
    reconciliation = coverage.monthly_reconciliation(frame)
    manifest_hash = mf.sha256_file(data_dir / mf.MANIFEST_NAME)
    proof = proof_mod.site_status(proof_mod.read_proof(PROOF_FILE), manifest_hash)
    return {
        "schema_version": 1,
        "source": f"data/{source}",
        "manifest_sha256": mf.sha256_file(data_dir / mf.MANIFEST_NAME),
        "sources": _source_rows(data_dir),
        "reference": _source_rows(REFERENCE),
        "reconciliation": {
            "tolerance": coverage.RECONCILIATION_TOLERANCE,
            "months": records(reconciliation, "month"),
        },
        "proof": proof,
    }


def _read_events(path: Path = REFERENCE / "events.csv") -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def markers_payload(data_dir: Path) -> dict:
    """markers.json: dated events for the charts, from the data itself or from cited reports."""
    frame = coverage.build_inputs(load_tables(data_dir))
    table = coverage.coverage_table(frame)
    changes = coverage.fill_source_gaps(frame[[c for c in frame.columns if c.startswith("chg_")]])

    step = ledger.step_down(table["issuance_gross_near"].dropna(), window=14)
    transition = step["transition_date"]
    transfers = coverage.internal_transfers_in(changes)
    transfer_day = transfers.idxmax()
    markers = [
        {
            "id": "issuance_step",
            "date": step["date"].date().isoformat(),
            "kind": "data",
            "label": (
                f"Daily gross issuance falls from about {step['before']:,.0f} to "
                f"{step['after']:,.0f} NEAR (14-day means)"
                + (f"; {transition.date().isoformat()} is a transition day" if transition else "")
            ),
            "evidence": (
                "supply_daily.parquet: issuance_gross_near, largest 14-day step down, dated to "
                "the first day closer to the new level"
            ),
            "sources": [],
        },
        {
            "id": "buyback_wallet_first_inflow",
            "date": table["buyback_near"].first_valid_index().date().isoformat(),
            "kind": "data",
            "label": f"First observed inflow to {coverage.BUYBACK_WALLET}",
            "evidence": "fee_wallet_inflows_daily.parquet: first day of the buyback wallet",
            "sources": [],
        },
        {
            "id": "internal_transfer",
            "date": transfer_day.date().isoformat(),
            "kind": "data",
            "label": (
                f"{transfers[transfer_day]:,.0f} NEAR moved between revenue wallets "
                "(netted out, not a buyback)"
            ),
            "evidence": "fee_wallet_inflows_daily.parquet: largest internal transfer",
            "sources": [],
        },
    ]
    not_drawn = []
    for event in _read_events():
        sources = event["sources"].split()
        if event["kind"] == "reported":
            markers.append(
                {
                    "id": f"reported_{event['date']}",
                    "date": event["date"],
                    "kind": "reported",
                    "label": event["label"],
                    "evidence": event["verified"],
                    "sources": sources,
                }
            )
        else:
            not_drawn.append(
                {"label": event["label"], "reason": event["verified"], "sources": sources}
            )
    return {
        "schema_version": 1,
        "markers": sorted(markers, key=lambda m: m["date"]),
        "not_drawn": not_drawn,
    }


def ots_files(out_dir: Path) -> list[Path]:
    """The OpenTimestamps file of the recorded run, served as is (empty before a stamp exists)."""
    record = proof_mod.read_proof(PROOF_FILE)
    if not record:
        return []
    stamp = PROOF_FILE.parent / PROOF_FILE.stem / record["run_id"] / "manifest.json.ots"
    return [copy_bytes(stamp, out_dir / "proof" / "manifest.json.ots")] if stamp.exists() else []


def copy_bytes(src: Path, dest: Path) -> Path:
    """The file as it is: a visitor hashes it in the browser to check the proof."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    return dest


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, allow_nan=False, indent=1) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def build_payloads(source: str, data_dir: Path) -> dict[str, dict]:
    """Every JSON payload of the site, by file name (without .json)."""
    return {
        "coverage": coverage_payload(data_dir, source),
        "distribution": distribution_payload(data_dir, source),
        "developer": developer_payload(data_dir, source),
        "valuation": valuation_payload(data_dir, source),
        "summary": summary_payload(data_dir, source),
        "queries": queries_payload(data_dir),
        "provenance": provenance_payload(data_dir, source),
        "markers": markers_payload(data_dir),
    }


def write_readme(path: Path, payloads: dict[str, dict]) -> Path:
    """README.md with its generated results block refreshed (the rest is kept as written)."""
    block, _ = thesis.render_results(payloads)
    text = thesis.replace_results((ROOT / "README.md").read_text(encoding="utf-8"), block)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def write_thesis(path: Path, payloads: dict[str, dict]) -> Path:
    text, _ = thesis.render(payloads)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def build(source: str, out_dir: Path = SITE_DATA) -> list[Path]:
    meta = {
        "built_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_commit": git_commit(),
        "source": f"data/{source}",
    }
    data_dir = ROOT / "data" / source
    payloads = build_payloads(source, data_dir)
    written = [write_json(out_dir / "meta.json", meta)]
    written += [write_json(out_dir / f"{name}.json", p) for name, p in payloads.items()]
    written += [copy_bytes(data_dir / mf.MANIFEST_NAME, out_dir / "snapshot-manifest.json")]
    written += ots_files(out_dir)
    if source == "snapshot":  # the committed thesis and README block come from the snapshot only
        home = ROOT if out_dir == SITE_DATA else out_dir
        written.append(write_thesis(home / "THESIS.md", payloads))
        written.append(write_readme(home / "README.md", payloads))
    return written
