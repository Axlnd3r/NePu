"""Break-even Intents volume V* and its sensitivity grid (see docs/METHODOLOGY.md)."""

from __future__ import annotations

from itertools import product

import pandas as pd

from capture.models.coverage import rolling_sum, tau_eff

INFLATION_GRID = (0.025, 0.016)
PRICE_MULTIPLIERS = (0.5, 1.0, 2.0)
TAU_MULTIPLIERS = (0.5, 1.0, 1.5)


def v_star(
    issuance_gross_near: pd.Series,
    burnt_near: pd.Series,
    near_usd: pd.Series,
    tau: pd.Series,
    window: int = 30,
) -> pd.Series:
    """Daily Intents volume (USD/day) at which tau_eff x volume equals net issuance in USD.

    V*(d) = (avg(issuance_gross_near) * near_usd(d) - avg(burnt_near * near_usd)) / tau,
    both averages over the same window.
    Net issuance below zero (burn above issuance) gives 0, not a negative volume.
    """
    issuance_avg = issuance_gross_near.rolling(window, min_periods=window).mean()
    burnt_usd_avg = (burnt_near * near_usd).rolling(window, min_periods=window).mean()
    net_usd = (issuance_avg * near_usd - burnt_usd_avg).clip(lower=0.0)
    return (net_usd / tau).where(tau > 0)


def tau_eff_buyback(
    buyback_near: pd.Series, near_usd: pd.Series, volume_usd: pd.Series, window: int
) -> pd.Series:
    """Variant of tau_eff counting only the buyback wallet's inflow (CR uses the same basis)."""
    buyback_usd = rolling_sum(buyback_near * near_usd, window)
    volume = rolling_sum(volume_usd, window)
    return (buyback_usd / volume).where((volume > 0) & (buyback_usd > 0))


def sensitivity_grid(
    total_supply_near: float,
    near_usd: float,
    burnt_near_avg: float,
    tau: float,
    inflations: tuple[float, ...] = INFLATION_GRID,
    price_multipliers: tuple[float, ...] = PRICE_MULTIPLIERS,
    tau_multipliers: tuple[float, ...] = TAU_MULTIPLIERS,
) -> pd.DataFrame:
    """V* for annual inflation i x price multiple x tau_eff multiple.

    Issuance per day = i * supply / 365 NEAR. Burn is held constant in NEAR, so its USD value scales
    with the price multiple together with issuance.
    """
    rows = []
    for i, pm, tm in product(inflations, price_multipliers, tau_multipliers):
        price, tau_used = near_usd * pm, tau * tm
        net_usd = max(i * total_supply_near / 365 * price - burnt_near_avg * price, 0.0)
        rows.append(
            {
                "inflation": i,
                "price_multiplier": pm,
                "tau_multiplier": tm,
                "near_usd": price,
                "tau_eff": tau_used,
                "v_star_usd_per_day": net_usd / tau_used,
            }
        )
    return pd.DataFrame(rows)


__all__ = ["sensitivity_grid", "tau_eff", "tau_eff_buyback", "v_star"]
