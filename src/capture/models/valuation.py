"""Valuation Lab: reverse break-even and Monte Carlo of the coverage ratio (docs/METHODOLOGY.md).

Pure functions. The USD price is an input held constant, never simulated: results are sensitivities
to a stated assumption, not forecasts. Every random draw comes from the generator passed in.

    CR_t = (tau * V_t + burn_near * P) / (i_t * S / 365 * P)

with V_t the 30-day average daily Intents volume (USD), tau the buyback take rate, P the NEAR price
and S the total supply (constant, as in V*).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import ceil

import numpy as np
import pandas as pd

SCENARIOS = ("historical", "decay", "flat")
HORIZONS_YEARS = (1, 3, 5)
CHECK_MONTHS = (12, 36, 60)
PERCENTILES = {"p10": 10, "p50": 50, "p90": 90}


@dataclass(frozen=True)
class Inputs:
    """Current state the simulation starts from (all measured, see build.valuation_payload)."""

    volume_usd_per_day: float
    total_supply_near: float
    near_usd: float
    burnt_near_per_day: float
    tau_min: float
    tau_max: float


def breakeven_volume(
    inflation: float, supply: float, price: float, burnt_near_per_day: float, tau: float
) -> float:
    """Daily volume (USD) at which CR = 1; 0 when burn alone covers issuance."""
    net_usd = max((inflation * supply / 365 - burnt_near_per_day) * price, 0.0)
    return net_usd / tau


def required_cagr(v0: float, v_star: float, years: float) -> float:
    """Compound annual growth taking volume from v0 to v_star; negative if v0 is already above."""
    return (v_star / v0) ** (1 / years) - 1


def reverse_table(
    inputs: Inputs,
    taus: dict[str, float],
    inflations: tuple[float, ...] = (0.025, 0.016),
    horizons: tuple[int, ...] = HORIZONS_YEARS,
) -> pd.DataFrame:
    """Required annual volume growth for CR = 1, tau and price held at their current values."""
    rows = []
    for horizon, inflation, (basis, tau) in product(horizons, inflations, taus.items()):
        v_star = breakeven_volume(
            inflation, inputs.total_supply_near, inputs.near_usd, inputs.burnt_near_per_day, tau
        )
        rows.append(
            {
                "horizon_years": horizon,
                "inflation": inflation,
                "basis": basis,
                "tau_eff": tau,
                "breakeven_volume_usd_per_day": v_star,
                "required_cagr": required_cagr(inputs.volume_usd_per_day, v_star, horizon),
            }
        )
    return pd.DataFrame(rows)


def inflation_path(
    months: int,
    start: float,
    end: float | None = None,
    ramp_months: int = 24,
    delay_months: int = 0,
) -> np.ndarray:
    """Annual inflation in months 1..months: constant, or held for delay_months, then linear from
    start to end over ramp_months, then held at end."""
    if end is None:
        return np.full(months, start)
    t = np.arange(1, months + 1) - delay_months
    return start + (end - start) * np.clip(t / ramp_months, 0.0, 1.0)


def monthly_log_growth(volume_usd: pd.Series, start: str | pd.Timestamp) -> pd.Series:
    """Log change of the monthly average of daily volume, from the month after `start`."""
    daily = volume_usd.dropna()
    monthly = daily[daily.index >= pd.Timestamp(start)].resample("MS").mean().dropna()
    return np.log(monthly).diff().dropna()


def block_bootstrap(
    growth: np.ndarray, n_paths: int, n_months: int, block: int, rng: np.random.Generator
) -> np.ndarray:
    """(n_paths, n_months) draws of consecutive blocks (moving blocks, no wrap-around)."""
    growth = np.asarray(growth, dtype=float)
    if len(growth) < block:
        raise ValueError(f"need at least one full block of {block} months, got {len(growth)}")
    n_blocks = ceil(n_months / block)
    starts = rng.integers(0, len(growth) - block + 1, size=(n_paths, n_blocks))
    index = starts[:, :, None] + np.arange(block)
    return growth[index].reshape(n_paths, n_blocks * block)[:, :n_months]


def scenario_growth(
    name: str, boot: np.ndarray, mu: float, half_life_months: float = 12
) -> np.ndarray:
    """Monthly log growth per path. mu is the sample mean of the bootstrapped history.

    historical: the draws as they are (their drift is the history's).
    flat: draws minus mu, so zero drift and the historical volatility.
    decay: flat draws plus a drift that starts at mu and halves every half_life_months.
    """
    if name == "historical":
        return boot
    centred = boot - mu
    if name == "flat":
        return centred
    if name == "decay":
        return centred + mu * 0.5 ** (np.arange(boot.shape[1]) / half_life_months)
    raise ValueError(f"unknown scenario {name!r}")


def volume_paths(growth: np.ndarray, v0: float) -> np.ndarray:
    """30-day average daily volume (USD) in months 1..n for every path."""
    return v0 * np.exp(np.cumsum(growth, axis=1))


def cr_paths(
    growth: np.ndarray,
    tau: np.ndarray,
    inflation: np.ndarray,
    inputs: Inputs,
    price_multiplier: float = 1.0,
) -> np.ndarray:
    """Coverage ratio in months 1..n for every path; price is constant at near_usd x multiplier."""
    price = inputs.near_usd * price_multiplier
    volume = volume_paths(growth, inputs.volume_usd_per_day)
    buyback_and_burn = tau[:, None] * volume + inputs.burnt_near_per_day * price
    issuance = inflation[None, :] * inputs.total_supply_near / 365 * price
    return buyback_and_burn / issuance


def summarize(cr: np.ndarray, check_months: tuple[int, ...] = CHECK_MONTHS) -> dict:
    """P(CR >= 1) at the check months, first-crossing month, and the fan of CR percentiles."""
    n_paths, n_months = cr.shape
    reached = cr >= 1.0
    ever = reached.any(axis=1)
    first = np.where(ever, reached.argmax(axis=1) + 1.0, np.inf)
    median_first = float(np.median(first))
    return {
        "p_cr_ge_1": {
            str(m): float(reached[:, m - 1].mean()) for m in check_months if m <= n_months
        },
        f"share_reaching_by_{n_months}": float(ever.mean()),
        "median_first_month": median_first if np.isfinite(median_first) else "not reached",
        "fan": {label: np.percentile(cr, q, axis=0).tolist() for label, q in PERCENTILES.items()},
    }


def monthly_tau(
    buyback_usd: pd.Series, volume_usd: pd.Series, min_coverage: float = 0.9
) -> pd.Series:
    """Buyback take rate per calendar month, from the days where both series exist.

    A month needs at least min_coverage of its days, so a month with a few observed days (the
    buyback wallet's first month) gives no value instead of a noisy one.
    """
    both = buyback_usd.notna() & volume_usd.notna()
    frame = pd.DataFrame({"buyback": buyback_usd[both], "volume": volume_usd[both]})
    grouped = frame.resample("MS")
    days, sums = grouped["buyback"].count(), grouped.sum()
    in_month = pd.Series(days.index.days_in_month, index=days.index)
    keep = (days / in_month >= min_coverage) & (sums["volume"] > 0)
    return (sums["buyback"] / sums["volume"])[keep]


def run_scenarios(
    inputs: Inputs,
    growth: np.ndarray,
    *,
    seed: int,
    n_paths: int,
    n_months: int,
    block: int,
    half_life_months: float,
    inflation_paths: dict[str, np.ndarray],
    price_multipliers: tuple[float, ...] = (0.5, 1.0, 2.0),
) -> list[dict]:
    """Every scenario x inflation path x price multiple, on the same draws (common random numbers).

    The block draws and the per-path tau (uniform between the observed monthly extremes) are made
    once, so the runs differ only in the assumption being varied.
    """
    rng = np.random.default_rng(seed)
    boot = block_bootstrap(growth, n_paths, n_months, block, rng)
    tau = rng.uniform(inputs.tau_min, inputs.tau_max, size=n_paths)
    mu = float(np.mean(growth))
    runs = []
    for scenario, (path, inflation), multiple in product(
        SCENARIOS, inflation_paths.items(), price_multipliers
    ):
        paths = scenario_growth(scenario, boot, mu, half_life_months)
        cr = cr_paths(paths, tau, inflation, inputs, multiple)
        volume = volume_paths(paths, inputs.volume_usd_per_day)
        volume_p50 = {
            str(m): float(np.median(volume[:, m - 1])) for m in CHECK_MONTHS if m <= n_months
        }
        runs.append(
            {"scenario": scenario, "inflation_path": path, "price_multiplier": multiple}
            | summarize(cr)
            | {"volume_p50_usd_per_day": volume_p50}
        )
    return runs
